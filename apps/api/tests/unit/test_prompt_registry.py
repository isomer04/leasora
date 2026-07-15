"""Prompt registry integrity gate.

Ensures every registered prompt carries version metadata, loads without its
frontmatter leaking into the body, and has a stable content hash.
"""

import pytest

from leasora_api.core.config import get_settings
from leasora_api.services.llm.registry import _parse_frontmatter, registry


async def test_sync_prompts_to_langfuse_noops_without_keys(monkeypatch):
    """Without Langfuse keys configured, sync must not raise and report synced=False.

    Explicitly force keys empty via monkeypatch: a developer's local .env may
    have real self-hosted Langfuse keys configured (conftest.py loads .env
    before test defaults), so "unset" can't be assumed as ambient state here.
    """
    monkeypatch.delenv("LEASORA_LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LEASORA_LANGFUSE_SECRET_KEY", raising=False)
    settings = get_settings()
    monkeypatch.setattr(settings, "langfuse_public_key", None)
    monkeypatch.setattr(settings, "langfuse_secret_key", None)
    # Force a fresh LangfuseClientWrapper._ensure_initialized() re-check by
    # resetting the shared singleton's cached init state.
    from leasora_api.core.langfuse_client import langfuse_client

    monkeypatch.setattr(langfuse_client, "_initialized", False)
    monkeypatch.setattr(langfuse_client, "_enabled", False)
    monkeypatch.setattr(langfuse_client, "_client", None)

    results = await registry.sync_prompts_to_langfuse()

    assert results, "Expected at least one prompt in the sync results"
    for name, version, synced in results:
        assert name in registry.list_prompts()
        assert version
        assert synced is False


def test_prompts_exist():
    prompts = registry.list_prompts()
    assert prompts, "Expected at least one registered prompt"


@pytest.mark.parametrize("name", registry.list_prompts())
def test_prompt_has_version_metadata(name: str):
    meta = registry.get_metadata(name)
    assert meta.version, f"Prompt '{name}' must declare a version"
    assert meta.description, f"Prompt '{name}' should declare a description"


@pytest.mark.parametrize("name", registry.list_prompts())
def test_load_prompt_strips_frontmatter(name: str):
    body = registry.load_prompt(name)
    assert not body.lstrip().startswith("---"), (
        f"Prompt '{name}' body still contains frontmatter"
    )
    assert body.strip(), f"Prompt '{name}' body is empty"


@pytest.mark.parametrize("name", registry.list_prompts())
def test_prompt_hash_is_stable(name: str):
    assert registry.get_prompt_hash(name) == registry.get_prompt_hash(name)


def test_parse_frontmatter_without_frontmatter_is_identity():
    text = "# Plain prompt\n{placeholder}"
    meta, body = _parse_frontmatter(text)
    assert meta == {}
    assert body == text


def test_parse_frontmatter_extracts_metadata():
    text = "---\nversion: 2\ndescription: hi\n---\n# Body\ncontent"
    meta, body = _parse_frontmatter(text)
    assert meta["version"] == "2"
    assert meta["description"] == "hi"
    assert body == "# Body\ncontent"
