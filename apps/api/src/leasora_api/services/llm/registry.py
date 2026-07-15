"""Prompt registry: versioned, metadata-carrying prompt loading.

Prompts live as Markdown files under ``prompts/`` and may declare YAML-style
frontmatter with at least a ``version``. The frontmatter is parsed for
metadata/versioning and stripped from the body returned by :meth:`load_prompt`,
so callers keep receiving the raw prompt text they format at call time.

Example prompt file::

    ---
    version: 1
    description: Classify a lease clause into a known type
    model: llama-3.1-8b-instant
    ---
    # Clause Classification Prompt
    ...
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PromptMetadata:
    """Metadata declared in a prompt's frontmatter."""

    version: str
    description: str = ""
    model: str = ""
    tags: list[str] = field(default_factory=list)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split optional ``---`` frontmatter from the prompt body.

    Uses :func:`yaml.safe_load` to parse the metadata block so values like 
    ``tags: [classification, ingest]`` are honored as actual lists instead 
    of being coerced through ``str.split(",")``.
    Strips the YAML block from the body so callers still get plain text.

    Returns:
        ``(metadata, body)`` tuple. If no frontmatter is present, the
        metadata dict is empty and the body is the original text.
    """
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines()
    # Find the closing delimiter (first '---' after the opening one).
    closing = next(
        (i for i in range(1, len(lines)) if lines[i].strip() == "---"),
        None,
    )
    if closing is None:
        return {}, text

    frontmatter_text = "\n".join(lines[1:closing])
    try:
        loaded = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        # Malformed YAML falls back to an empty metadata dict so a typo
        # in one prompt file doesn't take down every caller.
        loaded = {}
    if not isinstance(loaded, dict):
        loaded = {}

    # Coerce optional scalar fields to str; ``tags`` is forwarded as-is
    # (assumed to be a list of strings in the YAML).
    metadata = {
        key: str(loaded[key])
        for key in ("version", "description", "model")
        if key in loaded and loaded[key] is not None
    }
    raw_tags = loaded.get("tags")
    if isinstance(raw_tags, list):
        metadata["tags"] = ",".join(str(t) for t in raw_tags)

    body = "\n".join(lines[closing + 1 :]).lstrip("\n")
    return metadata, body


class PromptRegistry:
    """Manages prompt versioning and loading."""

    def __init__(self) -> None:
        self.prompts_dir = Path(__file__).parent / "prompts"

    def _read(self, name: str) -> str:
        path = self.prompts_dir / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        return path.read_text(encoding="utf-8")

    def load_prompt(self, name: str) -> str:
        """Load a prompt body (frontmatter stripped)."""
        _, body = _parse_frontmatter(self._read(name))
        return body

    def get_metadata(self, name: str) -> PromptMetadata:
        """Return declared metadata for a prompt.

        Falls back to the content hash as the version when no explicit
        ``version`` is declared, so every prompt always has a stable version.
        """
        meta, _ = _parse_frontmatter(self._read(name))
        tags = [t.strip() for t in meta.get("tags", "").strip("[]").split(",") if t.strip()]
        return PromptMetadata(
            version=meta.get("version") or self.get_prompt_hash(name),
            description=meta.get("description", ""),
            model=meta.get("model", ""),
            tags=tags,
        )

    def get_version(self, name: str) -> str:
        """Return the declared version (or content hash fallback)."""
        return self.get_metadata(name).version

    def get_prompt_hash(self, name: str) -> str:
        """Get SHA256 hash of the full prompt file (first 8 chars)."""
        content = self._read(name)
        return hashlib.sha256(content.encode()).hexdigest()[:8]

    def list_prompts(self) -> list[str]:
        """Return the names of all registered prompts.

        Documentation files (``README.md``) are intentionally excluded —
        this registry only carries loadable prompt templates.
        """
        return sorted(p.stem for p in self.prompts_dir.glob("*.md") if p.stem != "README")

    async def sync_prompts_to_langfuse(self) -> list[tuple[str, str, bool]]:
        """Sync all registered prompts to the Langfuse prompt registry.

        No-ops cleanly (returns all-False results) when Langfuse is not
        configured, via ``langfuse_client``'s graceful no-op behavior.

        Returns:
            List of ``(name, version, synced)`` tuples, one per prompt.
        """
        from leasora_api.core.langfuse_client import langfuse_client

        results: list[tuple[str, str, bool]] = []
        for name in self.list_prompts():
            version = self.get_version(name)
            body = self.load_prompt(name)
            synced = langfuse_client.create_prompt(name, body, version)
            results.append((name, version, synced))
        return results


registry = PromptRegistry()
