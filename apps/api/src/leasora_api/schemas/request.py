from pydantic import BaseModel, Field, ConfigDict, field_validator


class LeaseMetadata(BaseModel):
    """Metadata about a lease document."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "lease-123",
                "name": "Office Space Lease",
                "tenant": "John Doe",
                "landlord": "ABC Properties",
                "start_date": "2024-01-01",
                "end_date": "2026-12-31",
                "rent_amount": "$5,000/month",
                "location": "123 Main St, New York, NY 10001"
            }
        }
    )
    
    id: str = Field(..., description="Unique lease identifier")
    name: str = Field(..., description="Human-readable lease name")
    tenant: str = Field(..., description="Tenant name")
    landlord: str = Field(..., description="Landlord name")
    start_date: str = Field(..., description="Lease start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="Lease end date (YYYY-MM-DD)")
    rent_amount: str = Field(..., description="Monthly rent amount")
    location: str = Field(..., description="Property location")
    chunk_count: int | None = Field(
        default=None, description="Number of indexed chunks from ingestion"
    )
    created_at: str | None = Field(
        default=None, description="ISO timestamp of when the lease was uploaded"
    )


class AskRequest(BaseModel):
    """Request to ask a question about a lease."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lease_id": "lease-123",
                "question": "What are the maintenance responsibilities?"
            }
        }
    )
    
    lease_id: str = Field(..., description="ID of the lease document")
    question: str = Field(..., description="Question to ask about the lease", min_length=1, max_length=1000)


class CompareRequest(BaseModel):
    """Request to compare exactly two distinct leases.

    v1 scope: the response schema (``ComparisonDifference``) and the
    compare page UI both hardcode a two-lease shape (fixed
    ``lease1_value``/``lease2_value`` fields, two hardcoded table columns),
    so N-way comparison isn't representable yet. Constrained to exactly two
    distinct IDs here rather than accepted and silently mishandled
    downstream. N-way comparison is a tracked follow-up requiring a schema
    + UI rework.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lease_ids": ["lease-123", "lease-456"]
            }
        }
    )
    
    lease_ids: list[str] = Field(
        ..., description="Exactly two distinct lease IDs to compare", min_length=2, max_length=2
    )

    @field_validator("lease_ids")
    @classmethod
    def _reject_duplicate_lease_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("lease_ids must contain two distinct lease IDs, not the same ID twice")
        # Validate each lease_id against the same format contract used by
        # per-lease routes (see ``validate_lease_id`` in ``core/validators``).
        # This ensures malformed payloads fail with a 422 before reaching
        # the comparison service or vector store.
        from leasora_api.core.validators import validate_lease_id

        for lease_id in value:
            validate_lease_id(lease_id)
        return value


class UploadRequest(BaseModel):
    """Metadata for lease upload."""
    name: str = Field(..., description="Lease name", min_length=1, max_length=255)
    tenant: str = Field(default="", description="Tenant name")
    landlord: str = Field(default="", description="Landlord name")
