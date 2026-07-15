"""LLM-powered lease comparison service.

Compares exactly two leases (see ``CompareRequest`` for the v1 two-lease
scope decision): loads each lease's indexed chunks, groups them by clause
type, and for each clause type shared by both leases asks the LLM to
identify meaningful differences. Clause types present in only one lease
skip the LLM entirely and get a deterministic "present/missing" difference.

Concurrency: shared-clause-type LLM calls are parallelized with
``asyncio.gather`` over ``asyncio.to_thread`` (``complete_structured`` is
synchronous), bounded by a semaphore so a lease with many clause types
can't fire dozens of simultaneous calls. Each call has its own timeout, and
the overall fan-out has a separate outer timeout. Per-clause failures
(``LLMError``, timeout, or schema-invalid JSON) are caught independently —
one bad clause type never takes down the others.
"""

import asyncio
import logging
import math
from typing import Any

from pydantic import ValidationError

from leasora_api.core.config import get_settings
from leasora_api.core.exceptions import LLMError, NotFoundError
from leasora_api.core.langfuse_client import langfuse_client
from leasora_api.core.security import redact_pii
from leasora_api.schemas.domain import ClauseComparisonResult
from leasora_api.schemas.response import ComparisonDifference, CompareResponse
from leasora_api.services.ingest.lease_store import lease_store
from leasora_api.services.llm.groq_client import MAX_ATTEMPTS, groq_client
from leasora_api.services.llm.registry import registry
from leasora_api.services.rag.safety import sanitize_chunk
from leasora_api.services.retrieval.vector_store import RetrievalResult, VectorStore, chroma

logger = logging.getLogger(__name__)

"""Module constants for comparison pipeline.

Internal limits: clause-text cap, one-sided excerpt length. Tunable settings
are in Settings; these module-level constants are reserved for fixed internal
thresholds that don't need a deployment knob.
"""
_MAX_CLAUSE_TEXT_CHARS = 4000
_ONE_SIDED_EXCERPT_CHARS = 300  # Excerpt length for deterministic "present/missing" difference


class ComparisonService:
    """Compares two leases clause-type by clause-type using the LLM."""

    def __init__(self, vector_store: VectorStore | None = None) -> None:
        self._vector_store = vector_store if vector_store is not None else chroma
        self._llm_client = groq_client

    async def compare(self, lease_ids: list[str]) -> CompareResponse:
        """Compare exactly two leases and return their differences.

        Args:
            lease_ids: Exactly two distinct lease IDs (validated upstream by
                ``CompareRequest``).

        Returns:
            Aggregated comparison result.

        Raises:
            NotFoundError: If either lease doesn't exist or has no indexed
                chunks.
            LLMError: If every shared clause-type comparison fails (total
                failure) — a partial failure (some clause types succeed)
                is instead reflected as a note in ``key_insights``.
        """
        lease1_id, lease2_id = lease_ids[0], lease_ids[1]

        lease1_name, chunks1 = await self._load_lease(lease1_id)
        lease2_name, chunks2 = await self._load_lease(lease2_id)

        settings = get_settings()
        groups1 = self._group_by_clause_type(chunks1, settings.compare_max_chunks_per_lease)
        groups2 = self._group_by_clause_type(chunks2, settings.compare_max_chunks_per_lease)

        shared_types = sorted(set(groups1) & set(groups2))
        only_in_1 = sorted(set(groups1) - set(groups2))
        only_in_2 = sorted(set(groups2) - set(groups1))

        differences: list[ComparisonDifference] = []
        key_insights: list[str] = []

        if shared_types:
            llm_differences, llm_insights, attempted, failed = await self._compare_shared_types(
                shared_types, groups1, groups2, lease1_name, lease2_name
            )
            differences.extend(llm_differences)
            key_insights.extend(llm_insights)

            if attempted and failed == attempted:
                # Total failure across every shared clause type. If there's
                # nothing else to fall back on (no one-sided clauses either),
                # surface this as an error rather than an empty success.
                if not only_in_1 and not only_in_2:
                    raise LLMError(
                        "Comparison failed: the LLM could not compare any shared clause types"
                    )
                key_insights.append(
                    "Note: the LLM comparison failed for all shared clause types; "
                    "showing only clause types unique to one lease."
                )
            elif failed:
                key_insights.append(
                    f"Note: comparison failed for {failed} of {attempted} shared clause "
                    "type(s); showing partial results."
                )

        for clause_type in only_in_1:
            differences.append(
                self._one_sided_difference(clause_type, groups1[clause_type], lease1_name, lease2_name)
            )
            key_insights.append(
                f"'{clause_type}' clause found only in {lease1_name}, not in {lease2_name}."
            )

        for clause_type in only_in_2:
            differences.append(
                self._one_sided_difference(
                    clause_type, groups2[clause_type], lease2_name, lease1_name, swap=True
                )
            )
            key_insights.append(
                f"'{clause_type}' clause found only in {lease2_name}, not in {lease1_name}."
            )

        return CompareResponse(
            lease_ids=[lease1_id, lease2_id],
            differences=differences,
            key_insights=key_insights,
        )

    async def _load_lease(self, lease_id: str) -> tuple[str, list[RetrievalResult]]:
        """Look up a lease's display name and indexed chunks.

        Raises:
            NotFoundError: If the lease record doesn't exist, or exists but
                has no indexed chunks (nothing to compare).
        """
        lease = lease_store.get(lease_id)
        if lease is None:
            raise NotFoundError(f"Lease {lease_id} not found")

        chunks = await self._vector_store.get_by_lease(lease_id)
        if not chunks:
            raise NotFoundError(f"Lease {lease_id} has no indexed chunks to compare")

        return lease.name, chunks

    @staticmethod
    def _group_by_clause_type(
        chunks: list[RetrievalResult], max_chunks_per_type: int
    ) -> dict[str, list[RetrievalResult]]:
        """Group chunks by clause type, capping each group's size.

        Args:
            chunks: All chunks for a lease.
            max_chunks_per_type: Cap applied per clause type (bounds tokens
                per comparison prompt).

        Returns:
            Mapping of clause_type -> chunks (capped), preserving original
            relative order within each group.
        """
        groups: dict[str, list[RetrievalResult]] = {}
        for chunk in chunks:
            clause_type = str(chunk["metadata"].get("clause_type", "other"))
            bucket = groups.setdefault(clause_type, [])
            if len(bucket) < max_chunks_per_type:
                bucket.append(chunk)
        return groups

    async def _compare_shared_types(
        self,
        shared_types: list[str],
        groups1: dict[str, list[RetrievalResult]],
        groups2: dict[str, list[RetrievalResult]],
        lease1_name: str,
        lease2_name: str,
    ) -> tuple[list[ComparisonDifference], list[str], int, int]:
        """Run bounded, parallel LLM comparisons for every shared clause type.

        Returns:
            Tuple of (differences, insights, attempted_count, failed_count).
        """
        template = registry.load_prompt("compare_leases")
        settings = get_settings()
        max_concurrent = settings.compare_max_concurrent_llm_calls
        per_clause_timeout = settings.compare_per_clause_timeout_seconds
        overall_buffer = settings.compare_overall_timeout_buffer_seconds
        prompt_version = registry.get_version("compare_leases")
        semaphore = asyncio.Semaphore(max_concurrent)

        prompts: list[tuple[str, str]] = []
        for clause_type in shared_types:
            lease1_text = self._join_clause_text(groups1[clause_type])
            lease2_text = self._join_clause_text(groups2[clause_type])
            prompt = template.format(
                clause_type=clause_type,
                lease1_name=lease1_name,
                lease1_clauses=lease1_text,
                lease2_name=lease2_name,
                lease2_clauses=lease2_text,
            )
            prompts.append((clause_type, prompt))

        tasks = [
            self._call_llm_for_clause(
                clause_type, prompt, semaphore, prompt_version, per_clause_timeout
            )
            for clause_type, prompt in prompts
        ]

        try:
            # Scale the outer deadline with the number of shared clause
            # types: with concurrency capped at compare_max_concurrent_llm_calls,
            # the worst case is ceil(len(tasks) / max_concurrent) sequential
            # batches, each bounded by compare_per_clause_timeout_seconds.
            # A single clause call can internally retry up to MAX_ATTEMPTS
            # times (see groq_client._call_groq) before raising, so the
            # per-clause-timeout term must be scaled by MAX_ATTEMPTS to
            # cover the worst-case retry budget — otherwise the outer
            # wait_for fires before a retrying call could ever finish,
            # cancelling the whole gather and discarding already-completed
            # results. Plus a small buffer so the outer timeout doesn't
            # race the last in-flight call's own per-clause deadline.
            batch_count = math.ceil(len(tasks) / max_concurrent)
            overall_timeout = (
                batch_count * per_clause_timeout * MAX_ATTEMPTS + overall_buffer
            )
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=overall_timeout,
            )
        except TimeoutError:
            logger.error("Comparison timed out waiting on %d shared clause type(s)", len(tasks))
            # Every attempted call is considered failed if the overall
            # fan-out itself timed out.
            return [], [], len(tasks), len(tasks)

        differences: list[ComparisonDifference] = []
        insights: list[str] = []
        failed = 0

        for (clause_type, _prompt), result in zip(prompts, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "Comparison LLM call failed for clause type '%s': %s", clause_type, result
                )
                failed += 1
                continue

            parsed = self._parse_clause_result(clause_type, result)
            if parsed is None:
                failed += 1
                continue

            for diff in parsed.differences:
                differences.append(
                    ComparisonDifference(
                        clause_type=diff.clause_type or clause_type,
                        lease1_value=diff.lease1_value,
                        lease2_value=diff.lease2_value,
                        difference=diff.difference,
                    )
                )
            if parsed.insight:
                insights.append(parsed.insight)

        return differences, insights, len(prompts), failed

    async def _call_llm_for_clause(
        self,
        clause_type: str,
        prompt: str,
        semaphore: asyncio.Semaphore,
        prompt_version: str | None = None,
        per_clause_timeout: float | None = None,
    ) -> dict[str, Any]:
        """Run a single per-clause-type LLM call, bounded by the semaphore.

        Raises whatever exception the call raises (timeout, LLMError, etc.)
        so the caller's ``gather(..., return_exceptions=True)`` can catch it
        independently per clause type.

        The ``prompt_version`` is forwarded into the Langfuse span metadata
        so traces can be filtered by the exact prompt revision that produced them.
        """
        timeout = per_clause_timeout or get_settings().compare_per_clause_timeout_seconds
        metadata: dict[str, Any] = {"clause_type": clause_type}
        if prompt_version:
            metadata["prompt_version"] = prompt_version
        async with semaphore:
            with langfuse_client.start_generation(
                "compare-clause",
                model=self._llm_client.model,
                input=redact_pii(prompt),
                metadata=metadata,
            ) as generation_span:
                # `complete_structured` already accepts a `timeout` that
                # `_call_groq` treats as one overall deadline shared across
                # all retry attempts (not a fresh budget per attempt), so we
                # don't also wrap the asyncio.to_thread hop in
                # `asyncio.wait_for` — that would double-wrap the same
                # deadline and race with the SDK's own timeout handling.
                raw_output, usage = await asyncio.to_thread(
                    self._llm_client.complete_structured,
                    prompt,
                    0.3,
                    timeout,
                )
                generation_span.update(output=redact_pii(str(raw_output)), usage_details=usage)
            return raw_output

    @staticmethod
    def _parse_clause_result(
        clause_type: str, raw_output: dict[str, Any]
    ) -> ClauseComparisonResult | None:
        """Validate the LLM's per-clause JSON output against the expected shape.

        Returns:
            The validated result, or ``None`` if validation fails (missing
            key or wrong type) — treated identically to an `LLMError` by the
            caller (logged and dropped).
        """
        try:
            return ClauseComparisonResult.model_validate(raw_output)
        except ValidationError:
            logger.warning(
                "Comparison LLM output failed schema validation for clause type '%s': %s",
                clause_type,
                redact_pii(str(raw_output)[:200]),
            )
            return None

    @staticmethod
    def _join_clause_text(chunks: list[RetrievalResult]) -> str:
        """Sanitize and join chunk texts for a single lease's prompt section."""
        text = "\n\n".join(sanitize_chunk(chunk["text"]) for chunk in chunks)
        return text[:_MAX_CLAUSE_TEXT_CHARS]

    @staticmethod
    def _one_sided_difference(
        clause_type: str,
        chunks: list[RetrievalResult],
        present_lease_name: str,
        absent_lease_name: str,
        swap: bool = False,
    ) -> ComparisonDifference:
        """Build a deterministic difference for a clause type found in only one lease.

        Args:
            clause_type: The clause type present in only one lease.
            chunks: That lease's chunks for the clause type (used for the excerpt).
            present_lease_name: Name of the lease that has this clause type.
            absent_lease_name: Name of the lease that doesn't.
            swap: If True, the present lease's excerpt goes in
                ``lease2_value`` instead of ``lease1_value`` (used when the
                clause type is only in lease 2, so the row still reads
                left-to-right as [lease1, lease2]).
        """
        excerpt = redact_pii(chunks[0]["text"][:_ONE_SIDED_EXCERPT_CHARS]) if chunks else ""
        difference_text = f"Present in {present_lease_name} but missing from {absent_lease_name}"

        if swap:
            return ComparisonDifference(
                clause_type=clause_type,
                lease1_value="Not present",
                lease2_value=excerpt,
                difference=difference_text,
            )
        return ComparisonDifference(
            clause_type=clause_type,
            lease1_value=excerpt,
            lease2_value="Not present",
            difference=difference_text,
        )


comparison_service = ComparisonService()
