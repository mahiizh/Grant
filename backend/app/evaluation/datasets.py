import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CategoryType = Literal["fact", "multi_hop", "global", "unanswerable", "paraphrase", "multi_turn"]
OptimalStrategyType = Literal["vector", "graph", "hybrid", "abstain", "cache"]
SplitType = Literal["dev", "test"]


class GoldenQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    category: CategoryType
    split: SplitType = "dev"
    query: str
    expected_answer: str | None = None
    expected_doc_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_entities: list[str] = Field(default_factory=list)
    expected_path: list[str] | None = None
    optimal_strategy: OptimalStrategyType
    thread_turns: list[dict[str, str]] = Field(default_factory=list)
    expected_rewritten_query: str | None = None
    # Parent question(s) that must run first in the same orchestrator. Used by
    # paraphrase rows so the cache is populated naturally, never pre-seeded.
    depends_on: list[str] = Field(default_factory=list)


class GoldenDataset:
    def __init__(self, questions: list[GoldenQuestion]) -> None:
        self._questions = questions
        self._by_id = {q.id: q for q in questions}

    @classmethod
    def load_from_jsonl(cls, file_path: Path | str) -> "GoldenDataset":
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Golden dataset file not found at: {path}")

        questions: list[GoldenQuestion] = []
        with path.open(mode="r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                try:
                    data = json.loads(stripped)
                    questions.append(GoldenQuestion.model_validate(data))
                except Exception as e:
                    raise ValueError(
                        f"Error parsing golden dataset line {line_number} in {path}: {e}"
                    ) from e

        return cls(questions)

    @classmethod
    def load_from_dir(cls, directory: Path | str) -> "GoldenDataset":
        """Load every ``*.jsonl`` golden file in a directory (questions + multi-turn)."""
        root = Path(directory)
        if not root.exists():
            raise FileNotFoundError(f"Golden dataset directory not found at: {root}")

        questions: list[GoldenQuestion] = []
        for path in sorted(root.glob("*.jsonl")):
            questions.extend(cls.load_from_jsonl(path).questions)
        return cls(questions)

    def filter_by_category(self, category: CategoryType) -> list[GoldenQuestion]:
        return [q for q in self._questions if q.category == category]

    def filter_by_split(self, split: SplitType) -> "GoldenDataset":
        return GoldenDataset([q for q in self._questions if q.split == split])

    def get_by_id(self, question_id: str) -> GoldenQuestion | None:
        return self._by_id.get(question_id)

    def missing_chunk_ids(self, existing_chunk_ids: set[str]) -> list[tuple[str, str]]:
        """Return ``(question_id, chunk_id)`` pairs whose expected chunk does not exist."""
        missing: list[tuple[str, str]] = []
        for question in self._questions:
            for chunk_id in question.expected_chunk_ids:
                if chunk_id not in existing_chunk_ids:
                    missing.append((question.id, chunk_id))
        return missing

    @property
    def questions(self) -> list[GoldenQuestion]:
        return self._questions

    @property
    def categories(self) -> set[str]:
        return {q.category for q in self._questions}

    @property
    def splits(self) -> set[str]:
        return {q.split for q in self._questions}

    def summary(self) -> dict[str, int]:
        counts = Counter(q.category for q in self._questions)
        result: dict[str, int] = {str(k): v for k, v in counts.items()}
        result["total"] = len(self._questions)
        return result

    def split_summary(self) -> dict[str, int]:
        counts = Counter(q.split for q in self._questions)
        result: dict[str, int] = {str(k): v for k, v in counts.items()}
        result["total"] = len(self._questions)
        return result

    def __len__(self) -> int:
        return len(self._questions)

    def __iter__(self) -> Iterator[GoldenQuestion]:
        return iter(self._questions)
