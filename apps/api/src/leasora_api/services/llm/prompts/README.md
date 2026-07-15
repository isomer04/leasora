# Prompt Templates

LLM prompts live in this directory as Markdown files with YAML front-matter
(version, description, model, tags) and a `{placeholder}`-templated body.

## Output-spec convention

All prompt templates that ask the model to return a JSON object **must**
follow **Convention A — bare inline JSON**:

> Respond with ONLY a JSON object in this exact form, no other text:
> `{{"key": "value", ...}}`

Rules:
1. The example JSON object is rendered **inline** in the body of the
   instruction prose — **never** inside a markdown code fence.
2. Template placeholders use `{{...}}` doubled braces so a downstream
   ``str.format(**...)`` call doesn't try to expand them.
3. Each prompt that returns JSON ends with this exact phrase: `Respond
   with ONLY a JSON object in this exact form, no other text:`.

The CI check `scripts/check_prompts.py` walks every `*.md` file in this
directory and fails the build on any fenced JSON example (`` ```json ``
or `` ``` `` containing a JSON literal).

## Conventions applied

| Prompt                  | JSON shape style | Status |
|-------------------------|------------------|----------------|
| `answer_question.md`    | bare inline JSON | compliant |
| `compare_leases.md`     | bare inline JSON | compliant |
| `extract_lease_metadata.md` | already uses natural-language "JSON object, no explanation" — same family | compliant |
| `extract_signals.md`    | bare inline JSON | compliant |

## Adding a new template

1. Pick a stable filename; update `__init__.py` / registry if it should be
   importable.
2. Include the YAML front-matter block (version, description, model, tags).
3. If the prompt asks for JSON, follow Convention A above. Run
   `python scripts/check_prompts.py` before committing.
4. Add a regression test under `tests/evals/`.
