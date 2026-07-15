"""Application exception hierarchy.

Separates domain exceptions from HTTP presentation. Domain exceptions
are caught at the route layer and translated to appropriate HTTP responses,
allowing business logic to remain framework-agnostic.
"""


class LeasoraError(Exception):
    """Base exception for all Leasora domain errors."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        """Initialize exception with message and optional error code.

        Args:
            message: Human-readable error description
            error_code: Machine-readable error identifier for clients
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__

    @property
    def headers(self) -> dict[str, str] | None:
        """Optional HTTP response headers to attach to the error response.

        Subclasses can override to convey retry hints (``Retry-After``) or
        other transport-layer info; returns ``None`` when no extra headers
        are needed.
        """
        return None


class ValidationError(LeasoraError):
    """Raised when input validation fails."""

    pass


class NotFoundError(LeasoraError):
    """Raised when a requested resource does not exist."""

    pass


class ResourceExistsError(LeasoraError):
    """Raised when attempting to create a duplicate resource."""

    pass


class LLMError(LeasoraError):
    """Raised when LLM service fails or times out."""

    pass


class ParseError(LeasoraError):
    """Raised when parsing/deserialization fails."""

    pass


class IngestError(LeasoraError):
    """Raised when document ingestion fails."""

    pass


class IdempotencyKeyError(LeasoraError):
    """Raised when idempotency key validation fails."""

    pass


class RateLimitError(LeasoraError):
    """Raised when rate limit is exceeded.

    Optionally carries a ``retry_after`` (seconds) hint that the middleware
    layer surfaces as a ``Retry-After`` header so clients can back off
    automatically instead of guessing.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, error_code)
        self.retry_after = retry_after

    @property
    def headers(self) -> dict[str, str] | None:
        if self.retry_after is None:
            return None
        return {"Retry-After": str(self.retry_after)}


EXCEPTION_TO_STATUS_CODE: dict[type[LeasoraError], int] = {
    ValidationError: 422,
    NotFoundError: 404,
    ResourceExistsError: 409,
    LLMError: 503,
    ParseError: 400,
    IngestError: 400,
    IdempotencyKeyError: 409,
    RateLimitError: 429,
}
