"""Golden dataset schema and loader for retrieval/answer evaluation.

The golden dataset is a JSONL file where each line is a ``GoldenQuestion``:
a question about the demo lease fixture, the ground-truth clause IDs that
should be retrieved, a reference answer, a category, and whether the system
should refuse rather than answer. Ground-truth clause IDs are pinned to the
chunk IDs produced by ingesting ``data/test-fixtures/demo_lease.pdf`` with
``lease_id="golden-demo-lease"`` (see ``tests/evals/golden/README.md``).
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

QuestionCategory = Literal["factual", "statute", "red_flag", "out_of_scope"]

# apps/api/src/leasora_api/services/eval/golden.py -> apps/api/tests/evals/golden
GOLDEN_DIR = Path(__file__).resolve().parents[4] / "tests" / "evals" / "golden"


class GoldenQuestion(BaseModel):
    """A single labeled question in the golden evaluation dataset."""

    question: str = Field(..., description="The natural-language question to ask")
    relevant_clause_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Ground-truth chunk IDs (from the golden-demo-lease fixture) that "
            "are relevant to answering this question. Empty for should_refuse "
            "questions."
        ),
    )
    reference_answer: str = Field(
        default="", description="A reference answer used for answer-quality scoring"
    )
    category: QuestionCategory = Field(..., description="Question category")
    should_refuse: bool = Field(
        default=False,
        description="True if the system should refuse rather than answer",
    )


def load_golden_dataset(path: str | Path) -> list[GoldenQuestion]:
    """Load the golden dataset from a JSONL file.

    Args:
        path: Path to the ``.jsonl`` golden dataset file.

    Returns:
        List of parsed and validated ``GoldenQuestion`` entries.
    """
    dataset_path = Path(path)
    questions: list[GoldenQuestion] = []
    with dataset_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            questions.append(GoldenQuestion.model_validate(json.loads(line)))
    return questions
