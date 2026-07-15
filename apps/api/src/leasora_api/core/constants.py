"""Application-wide constants for maintainability."""

APP_VERSION = "0.2.0"

# Feature flags for incomplete integrations (marked for future work)
UPLOAD_INTEGRATION_MESSAGE = (
    "Lease uploaded and being analyzed - integrate with ingest service"
)
EVALUATION_INTEGRATION_MESSAGE = "Evaluation service integration pending"

# Canonical refusal message: returned when retrieval confidence is too low
# to ground an answer. Returned verbatim with no LLM call, ensuring
# refusals are deterministic and cheap.
REFUSAL_MESSAGE = (
    "I don't have enough information in the lease to answer that. "
    "Please try a different question or upload a lease that covers this topic."
)
