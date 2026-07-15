from leasora_api.core.exceptions import ValidationError, NotFoundError


def test_validation_error():
    exc = ValidationError("Invalid input")
    assert exc.error_code == "ValidationError"
    assert exc.message == "Invalid input"


def test_not_found_error():
    exc = NotFoundError("Not found")
    assert exc.error_code == "NotFoundError"
    assert exc.message == "Not found"
