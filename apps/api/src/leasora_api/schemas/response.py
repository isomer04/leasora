from pydantic import BaseModel, Field, ConfigDict

from leasora_api.schemas.domain import MetadataExtractionStatus, SignalLabel
from leasora_api.schemas.request import LeaseMetadata


class MetadataRefreshResponse(BaseModel):
    """Outcome of an explicit metadata extraction retry."""

    status: MetadataExtractionStatus
    updated_fields: list[str]
    lease: LeaseMetadata


class SourceReference(BaseModel):
    """Reference to a source clause in the lease."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "clause_id": "clause-1",
                "clause_type": "maintenance",
                "excerpt": "Landlord is responsible for structural repairs",
                "source": "lease.pdf",
                "page": 2
            }
        }
    )
    
    clause_id: str = Field(..., description="ID of the clause")
    clause_type: str = Field(..., description="Type of clause (e.g., rental_term, maintenance)")
    excerpt: str = Field(..., description="Relevant excerpt from the clause")
    source: str | None = Field(default=None, description="Source document filename")
    page: int | None = Field(default=None, description="Page number where the clause appears")


class AskResponse(BaseModel):
    """Response to a question about a lease."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "The landlord is responsible for structural repairs according to section 4.2",
                "sources": [
                    {
                        "clause_id": "clause-1",
                        "clause_type": "maintenance",
                        "excerpt": "Landlord is responsible for structural repairs",
                        "source": "lease.pdf",
                        "page": 4
                    }
                ],
                "confidence": 0.95,
                "quote": "Landlord is responsible for structural repairs and roof maintenance.",
                "signal": "standard"
            }
        }
    )
    
    answer: str = Field(..., description="Grounded answer based on lease content")
    sources: list[SourceReference] = Field(default_factory=list, description="Source references")
    confidence: float = Field(default=0.85, description="Confidence score (0-1)")
    quote: str | None = Field(
        default=None,
        description="Verbatim quoted span from the lease that the answer is grounded in",
    )
    signal: SignalLabel | None = Field(
        default=None,
        description="How the relevant clause compares to standard lease practice",
    )


class ComparisonDifference(BaseModel):
    """A difference between leases."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "clause_type": "Rental Term",
                "lease1_value": "36 months",
                "lease2_value": "24 months",
                "difference": "12 months longer"
            }
        }
    )
    
    clause_type: str = Field(..., description="Type of clause")
    lease1_value: str = Field(..., description="Value in first lease")
    lease2_value: str = Field(..., description="Value in second lease")
    difference: str = Field(..., description="Description of the difference")


class CompareResponse(BaseModel):
    """Response comparing multiple leases."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lease_ids": ["lease-123", "lease-456"],
                "differences": [
                    {
                        "clause_type": "Rental Term",
                        "lease1_value": "36 months",
                        "lease2_value": "24 months",
                        "difference": "12 months longer"
                    }
                ],
                "key_insights": ["Lease 1 has a longer term with higher rent"]
            }
        }
    )
    
    lease_ids: list[str] = Field(..., description="IDs of compared leases")
    differences: list[ComparisonDifference] = Field(..., description="List of differences")
    key_insights: list[str] = Field(default_factory=list, description="Key insights from comparison")


class ComparisonCountResponse(BaseModel):
    """Total number of comparisons ever run, for the dashboard stat card."""
    model_config = ConfigDict(json_schema_extra={"example": {"count": 3}})

    count: int = Field(..., description="Total number of comparisons recorded", ge=0)


class ComparisonHistoryItem(BaseModel):
    """A single recorded comparison request."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "cmp_a1b2c3d4",
                "lease_ids": ["lease-123", "lease-456"],
                "created_at": "2026-01-01T12:00:00+00:00",
            }
        }
    )

    id: str = Field(..., description="Unique comparison record identifier")
    lease_ids: list[str] = Field(..., description="IDs of the leases that were compared")
    created_at: str = Field(..., description="ISO timestamp of when the comparison was run")


class ComparisonHistoryResponse(BaseModel):
    """A bounded, paginated page of past comparisons."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": "cmp_a1b2c3d4",
                        "lease_ids": ["lease-123", "lease-456"],
                        "created_at": "2026-01-01T12:00:00+00:00",
                    }
                ],
                "page": 1,
                "page_size": 20,
                "total": 1,
            }
        }
    )

    items: list[ComparisonHistoryItem] = Field(..., description="Comparison records for this page")
    page: int = Field(..., description="1-indexed page number returned", ge=1)
    page_size: int = Field(..., description="Number of records per page (server-capped)", ge=1)
    total: int = Field(..., description="Total number of comparison records", ge=0)


class ChunkResponse(BaseModel):
    """A single indexed clause/chunk belonging to a lease."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "lease_abc12345::0",
                "text": "Tenant shall pay monthly rent of $2,500 due on the 1st of each month.",
                "clause_type": "rental_term",
                "page": 1,
                "source": "lease_abc12345.pdf",
            }
        }
    )

    id: str = Field(..., description="Unique chunk identifier")
    text: str = Field(..., description="Full chunk text")
    clause_type: str = Field(..., description="Heuristically assigned clause type")
    page: int | None = Field(default=None, description="Page number the chunk was extracted from")
    source: str | None = Field(default=None, description="Source document filename")


class UploadResponse(BaseModel):
    """Response after uploading a lease."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lease_id": "lease-123",
                "name": "Office Space Lease",
                "status": "processing",
                "message": "Lease uploaded and being analyzed"
            }
        }
    )
    
    lease_id: str = Field(..., description="ID of the uploaded lease")
    name: str = Field(..., description="Lease name")
    status: str = Field(..., description="Upload status (pending, processing, complete)")
    message: str = Field(..., description="Status message")


class HealthResponse(BaseModel):
    """Health check response."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "version": "0.2.0"
            }
        }
    )
    
    status: str = Field(..., description="Service status")
    version: str = Field(default="0.2.0", description="API version")
