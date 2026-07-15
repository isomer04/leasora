"""Test configuration.

Load a real .env if present before setting test defaults, allowing the default
fast suite to run without real secrets while letting LLM-as-judge tests pick up
a real LEASORA_GROQ_API_KEY from .env when run with `pytest -m eval` locally.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    _env_file = Path(__file__).resolve().parents[3] / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass

# Force a dummy LEASORA_GROQ_API_KEY when missing or explicitly empty.
if not os.environ.get("LEASORA_GROQ_API_KEY"):
    os.environ["LEASORA_GROQ_API_KEY"] = "test-key-123"

import pytest
from leasora_api.main import create_app

# Valid TCP port range constants (RFC 793: ephemeral ports 1-65535)
VALID_PORT_RANGE_MIN = 1
VALID_PORT_RANGE_MAX = 65535


@pytest.fixture
def app():
    """Create the FastAPI app."""
    return create_app()
