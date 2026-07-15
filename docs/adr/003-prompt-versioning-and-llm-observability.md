# ADR 003: Prompt Versioning and LLM Observability

**Date:** 2026-07-05
**Deciders:** Development Team

## Status: SUPERSEDED by ADR-007 — Retrieval Quality, Evaluation Harness, and LLM-as-Judge Guardrails

**Why superseded:** the prompt registry, LLM-as-judge guardrails, and Langfuse
integration described here were extended and partially re-implemented during the
retrieval-quality work recorded in
[ADR-007](007-retrieval-quality-and-evaluation.md). The original *spirit* — versioned
prompts, traceable LLM calls, validated outputs, and an injection-defense layer —
still holds. The *implementation details* in this ADR are stale in several places
(see below); ADR-007 is the load-bearing doc going forward.

**Implementation drift since 2026-07-05:**

- `services/llm/registry.py` uses **Markdown frontmatter** (with at least a
  `version:` field) and a `PromptMetadata` dataclass, not bare `.md` files
  synced directly to Langfuse on startup.
- The registry does **not** call `langfuse.create_prompt` at startup. Langfuse
  is opt-in via `langfuse_enabled=True` plus keys, and the client wrapper at
  `core/langfuse_client.py` is a graceful no-op when unconfigured.
- Generic OpenTelemetry in `core/tracing.py` is untouched; Langfuse
  observability was added **alongside** it (ADR-007 §6), not as a replacement.
- `sanitize_chunk` lives in `services/rag/safety.py`, is gated on
  `prompt_injection_defense_enabled` (default ON), and defaults to
  `max_length=2000`, not 1000.
- Eval scaffolding is bespoke golden fixtures + LLM-as-judge in
  `services/eval/` + `apps/api/tests/evals/`, not ragas/deepeval as described
  here.

If the original decisions in this ADR need to be re-litigated, do it in a new
ADR — do not edit this one.

## Context

LLM applications require:
1. **Prompt management:** Versioning prompts separately from code for rapid iteration
2. **Observability:** Tracing LLM calls to debug quality issues, track latency, and measure token usage
3. **Reproducibility:** Knowing exactly which prompt version generated a particular answer
4. **Safety:** Validating LLM outputs and detecting prompt injection attacks
5. **Evaluation:** Running automated evals (Ragas, DeepEval, Promptfoo) against eval fixtures

Previous implementations scattered prompts across the codebase and lacked centralized tracing, making it hard to correlate quality issues with specific prompts.

## Decision

### 1. Prompt Versioning via Files and Registry

**Structure:**

```
services/llm/prompts/
├── classify_clause.md           # Markdown template
├── answer_question.md
├── extract_signals.md
└── compare_leases.md
```

**Registry pattern:**

```python
# services/llm/registry.py
import hashlib
from pathlib import Path
from langfuse import Langfuse

class PromptRegistry:
    """Manages prompt versioning and syncing to Langfuse."""
    
    def __init__(self):
        self.prompts_dir = Path(__file__).parent / "prompts"
        self.langfuse = Langfuse()
    
    def load_prompt(self, name: str) -> str:
        """Load prompt from file (Markdown or Jinja)."""
        path = self.prompts_dir / f"{name}.md"
        return path.read_text()
    
    async def sync_prompts_to_langfuse(self):
        """Upload all prompts to Langfuse registry."""
        for prompt_file in self.prompts_dir.glob("*.md"):
            content = prompt_file.read_text()
            # Version = 8-char SHA256 hash (deterministic)
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:8]
            
            self.langfuse.create_prompt(
                name=prompt_file.stem,
                prompt=content,
                tags=["production"],
                version=hash_val,
            )

registry = PromptRegistry()
```

**Benefits:**

- Prompts are version-controlled alongside code
- Registry syncs to Langfuse at startup
- Version hashes are deterministic (same content = same hash)
- Easy to compare prompt changes via Git diff
- Rollback prompts by reverting Git commit

### 2. LLM Observability via Langfuse + OpenTelemetry

**Architecture:**

```
[FastAPI handler]
    ↓ (spans)
[OpenTelemetry OTLP exporter]
    ↓ (HTTP)
[Langfuse API / OTLP collector]
    ↓
[Langfuse dashboard]
  - Trace visualization
  - Token usage
  - Latency metrics
  - Prompt/model versions
```

**Groq client with auto-tracing:**

```python
# services/llm/groq_client.py
from groq import Groq
from opentelemetry import trace
from leasora_api.core.config import get_settings

tracer = trace.get_tracer(__name__)

class GroqClient:
    def __init__(self):
        settings = get_settings()
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = settings.groq_model
    
    def complete(self, prompt: str, **kwargs) -> str:
        """Sync LLM call with automatic tracing."""
        with tracer.start_as_current_span("groq.complete") as span:
            span.set_attribute("prompt_length", len(prompt))
            span.set_attribute("model", self.model)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
            )
            
            result = response.choices[0].message.content
            span.set_attribute("result_length", len(result))
            return result

groq = GroqClient()
```

**OpenTelemetry initialization:**

```python
# core/tracing.py
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from leasora_api.core.config import get_settings

def init_tracing():
    """Initialize OpenTelemetry SDK with Langfuse OTLP endpoint."""
    settings = get_settings()
    endpoint = settings.otlp_endpoint or "http://localhost:4317"
    
    exporter = OTLPSpanExporter(endpoint=endpoint)
    trace_provider = TracerProvider()
    trace_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(trace_provider)
```

**Local Langfuse setup:**

```yaml
# services/compose/docker-compose.yml
services:
  langfuse:
    image: langfuse/langfuse:latest
    ports:
      - "3000:3000"      # Web UI
      - "4317:4317"      # OTLP receiver
    environment:
      DATABASE_URL: postgresql://postgres:password@db:5432/langfuse
```

### 3. Safety: Output Validation and Prompt Injection Defense

**Structured output validation:**

```python
# services/rag/safety.py
from pydantic import BaseModel, ValidationError
import json

class LLMResponse(BaseModel):
    answer: str
    confidence: float
    sources: list[str]

def validate_llm_output(text: str) -> LLMResponse:
    """Parse and validate LLM output structure."""
    try:
        data = json.loads(text)
        return LLMResponse(**data)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response contains invalid JSON: {e}")
    except ValidationError as e:
        raise ValueError(f"LLM response failed validation: {e}")
```

**Prompt injection defense:**

```python
# services/rag/safety.py
import re

INJECTION_PATTERNS = [
    r"ignore.*instructions",
    r"forget.*system.*prompt",
    r"you.*are.*now",
    r"act.*as",
]

def check_prompt_injection(user_input: str) -> bool:
    """Detect common prompt injection patterns."""
    normalized = user_input.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, normalized):
            return True
    return False
```

**Chunk sanitization:**

```python
def sanitize_chunk(chunk: str, max_length: int = 1000) -> str:
    """Remove code, URLs, and enforce size limits."""
    # Remove common code markers
    chunk = re.sub(r"```[\s\S]*?```", "", chunk)
    # Remove URLs
    chunk = re.sub(r"https?://\S+", "", chunk)
    # Enforce max length
    return chunk[:max_length].strip()
```

### 4. Evaluation: Ragas + DeepEval

**Automated evals structure:**

```
tests/evals/
├── conftest.py           # Eval fixtures
├── golden/               # Synthetic eval data
│   ├── test_leases/
│   │   ├── lease_1_synthetic.pdf
│   │   └── lease_2_synthetic.pdf
│   └── expected_signals.json
├── test_ragas.py         # Faithfulness, context relevance
├── test_deepeval.py      # Custom metrics
└── test_prompt_regression.py  # Promptfoo comparison
```

**Example Ragas test:**

```python
# tests/evals/test_ragas.py
from ragas import evaluate
from ragas.metrics import Faithfulness, ContextRelevance

def test_ragas_faithfulness():
    """Evaluate answer faithfulness to retrieved context."""
    results = evaluate(
        dataset=eval_dataset,
        metrics=[Faithfulness(), ContextRelevance()],
    )
    assert results["faithfulness"] > 0.85
```

## Consequences

### Positive

- **Prompt iteration:** Change prompt, sync to Langfuse, test new version without deploying code
- **Debugging:** Traces show exact prompt, model, tokens, and latency for each LLM call
- **Evaluation:** Automated evals run against golden fixtures; catch regressions early
- **Reproducibility:** Version hash ensures same prompt generates same answer (deterministic)
- **Safety:** Injection defense, output validation, and sanitization built in
- **Governance:** Langfuse dashboard provides centralized view of LLM usage

### Negative

- **Infrastructure:** Requires Langfuse (or compatible OTLP receiver) running locally or in cloud
- **Latency:** OTLP export adds minimal overhead (~5ms per trace)
- **Complexity:** Developers must understand prompt registry and eval fixture format
- **Cost:** Hosted Langfuse charges based on traces (self-hosted is free)

### Mitigation

- **Self-hosted default:** Docker Compose includes Langfuse for local dev (see ADR 005)
- **Async export:** OTLP uses batch processor (doesn't block requests)
- **Documentation:** Examples and templates in ARCHITECTURE.md and docs/
- **Optional:** Langfuse integration is optional; traces work without it

## Related Decisions

- **ADR 005:** Self-host Langfuse by default for local dev and CI
- **ARCHITECTURE.md (§2.4):** RAG services architecture details

## References

- [Langfuse Documentation](https://langfuse.com/docs/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [Ragas Documentation](https://docs.ragas.io/)
- [DeepEval Documentation](https://docs.deepeval.ai/)
- [Prompt Injection Defense (OWASP)](https://owasp.org/www-community/attacks/Prompt_Injection)
