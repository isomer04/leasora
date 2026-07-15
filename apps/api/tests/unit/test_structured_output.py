"""Unit tests for the structured-output schema and query_service's validation path."""

import pytest
from pydantic import ValidationError

from leasora_api.schemas.domain import SignalLabel, StructuredAnswer
from leasora_api.schemas.response import AskResponse
from leasora_api.services.rag.query_service import RAGQueryService


def test_structured_answer_accepts_valid_payload():
    answer = StructuredAnswer.model_validate(
        {"answer": "Rent is due monthly.", "quote": "Rent is due.", "signal": "standard"}
    )
    assert answer.signal == SignalLabel.STANDARD


def test_structured_answer_rejects_missing_fields():
    with pytest.raises(ValidationError):
        StructuredAnswer.model_validate({"answer": "ok"})


def test_structured_answer_rejects_invalid_signal_value():
    with pytest.raises(ValidationError):
        StructuredAnswer.model_validate(
            {"answer": "ok", "quote": "ok", "signal": "not_a_real_signal"}
        )


def test_ask_response_quote_and_signal_default_to_none():
    response = AskResponse(answer="hello")
    assert response.quote is None
    assert response.signal is None


def test_ask_response_accepts_signal_and_quote():
    response = AskResponse(
        answer="hello", quote="verbatim text", signal=SignalLabel.RED_FLAG
    )
    assert response.signal == SignalLabel.RED_FLAG
    assert response.quote == "verbatim text"


def test_parse_structured_answer_returns_none_on_invalid_payload():
    result = RAGQueryService._parse_structured_answer({"answer": "ok"}, lease_id="lease-1")
    assert result is None


def test_parse_structured_answer_returns_model_on_valid_payload():
    payload = {"answer": "ok", "quote": "quoted text", "signal": "unusual"}
    result = RAGQueryService._parse_structured_answer(payload, lease_id="lease-1")
    assert result is not None
    assert result.signal == SignalLabel.UNUSUAL
