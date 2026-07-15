---
version: 2
description: Compare two leases' clauses of a shared clause type and identify key differences as structured JSON
model: llama-3.3-70b-versatile
tags: [rag, comparison, structured-output]
---
# Compare Lease Clauses

You are comparing two commercial lease documents. Below are the relevant clauses
about "{clause_type}" from each lease.

Lease 1 ({lease1_name}):
{lease1_clauses}

Lease 2 ({lease2_name}):
{lease2_clauses}

Identify the key differences between these leases regarding {clause_type}.

Respond with ONLY a JSON object in this exact form, no other text:
{{"differences": [{{"clause_type": "{clause_type}", "lease1_value": "<brief summary of Lease 1's position>", "lease2_value": "<brief summary of Lease 2's position>", "difference": "<concise description of how they differ>"}}], "insight": "<one-sentence key takeaway about this difference, or null if trivial>"}}
