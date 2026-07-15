---
version: 2
description: Extract structured lease metadata (parties, dates, rent, location) from relevant lease clauses as JSON
model: llama-3.3-70b-versatile
tags: [ingest, structured-output, extraction]
---
# Extract Lease Metadata

Given the following clauses from a commercial lease document, extract the fields below.
Use only information explicitly stated in the clauses. Do not infer or invent values.
Return a JSON object with exactly these keys:
- tenant: tenant/lessee legal name, or null if not found
- landlord: landlord/lessor legal name, or null if not found
- start_date: lease start date in YYYY-MM-DD format, or null if not found
- end_date: lease end date in YYYY-MM-DD format, or null if not found
- rent_amount: monthly rent amount as a string (e.g. "$5,000/month"), or null if not found
- location: property address/location, or null if not found

Clauses:
{chunks_text}

Respond with only the JSON object, no explanation.
