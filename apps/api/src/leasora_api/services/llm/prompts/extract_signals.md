---
version: 2
description: Identify key signals and risks in a lease excerpt as structured JSON
model: llama-3.3-70b-versatile
tags: [ingest, signals]
---
# Extract Lease Signals

Identify key signals and risks in this lease excerpt.

**Lease Text:**
{lease_text}

Respond with ONLY a JSON object in this exact form, no other text:
{{"signals": ["standard", "tenant_friendly", "landlord_friendly", "unusual", "red_flag"], "explanation": "..."}}