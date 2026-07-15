from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PromptContext(BaseModel):
    """Two-track prompt handling for PII security in LLM interactions.

    The LLM must see raw text (including real tenant names, addresses,
    contact info) to answer entity questions correctly. However, observability
    systems (logs, Langfuse traces) must never carry unredacted PII.

    This type enforces the contract: always create a single PromptContext
    per question, pass the redacted version to observability systems, and
    the raw version to the LLM. This centralizes the redaction logic and
    makes the security intent explicit.

    Example:
        prompt = PromptBuilder().build_prompt(context, question)
        pc = PromptContext(
            raw=prompt,
            redacted=redact_pii(prompt)
        )
        # Pass to LLM: pc.raw
        # Pass to Langfuse: pc.redacted
        # Pass to logs: pc.redacted
    """

    raw: str = Field(
        ..., description="Full prompt with real tenant/lease data; only for LLM consumption"
    )
    redacted: str = Field(
        ..., description="PII-redacted version; for logs, Langfuse, and other observability"
    )


class Clause(BaseModel):
    text: str
    clause_type: str


class SignalLabel(str, Enum):
    """Taxonomy for how a clause/answer compares to standard lease practice."""

    STANDARD = "standard"
    TENANT_FRIENDLY = "tenant_friendly"
    LANDLORD_FRIENDLY = "landlord_friendly"
    UNUSUAL = "unusual"
    RED_FLAG = "red_flag"


class Signal(BaseModel):
    name: str
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0 and 1")


class MetadataExtractionStatus(str, Enum):
    """Outcome of a metadata extraction attempt."""

    UPDATED = "updated"
    NO_FIELDS = "no_fields"
    FAILED = "failed"


class ExtractedLeaseMetadata(BaseModel):
    """Schema-constrained shape the LLM must return for metadata extraction.

    Used by ``GroqClient.complete_structured`` (JSON mode) and validated by
    ``MetadataExtractor`` before merging non-null fields into the lease
    store. All fields are optional/nullable since the LLM may not find a
    given field in the sampled chunks.
    """

    model_config = ConfigDict(extra="forbid")

    tenant: str | None = Field(default=None, description="Tenant/lessee legal name")
    landlord: str | None = Field(default=None, description="Landlord/lessor legal name")
    start_date: str | None = Field(default=None, description="Lease start date, YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="Lease end date, YYYY-MM-DD")
    rent_amount: str | None = Field(default=None, description="Monthly rent amount, e.g. '$5,000/month'")
    location: str | None = Field(default=None, description="Property address/location")


class ClauseComparisonDifference(BaseModel):
    """A single difference row within a per-clause-type comparison result."""

    clause_type: str
    lease1_value: str
    lease2_value: str
    difference: str


class ClauseComparisonResult(BaseModel):
    """Schema-constrained shape the LLM must return for one clause-type comparison.

    Used by ``GroqClient.complete_structured`` (JSON mode) and validated by
    ``ComparisonService`` before aggregating into ``CompareResponse``.
    ``complete_structured`` only guarantees valid JSON, not schema
    compliance — a missing key or wrong type here is treated as a
    per-clause failure (logged, dropped), never a crash.
    """

    differences: list[ClauseComparisonDifference] = Field(default_factory=list)
    insight: str | None = Field(default=None)


class StructuredAnswer(BaseModel):
    """Schema-constrained shape the LLM must return for ``answer_question``.

    Used by ``GroqClient.complete_structured`` (JSON mode) and validated by
    ``RAGQueryService`` before being mapped onto the public ``AskResponse``.
    Kept separate from ``AskResponse`` since the LLM has no knowledge of
    retrieval-derived fields like ``sources``/``confidence``.
    """

    answer: str = Field(..., description="Plain-English answer to the question")
    quote: str = Field(
        ..., description="Verbatim quoted span from the lease context supporting the answer"
    )
    signal: SignalLabel = Field(
        ..., description="How the relevant clause compares to standard lease practice"
    )
