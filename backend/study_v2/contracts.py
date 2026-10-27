"""Strict item contracts and request limits shared by generation and scoring."""

import os
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from fastapi import HTTPException
from backend.material_groups import selected_ids
from backend.ai.numerical import unit_info

KINDS = ("multiple_choice", "multiple_select", "short_answer", "numerical")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Citation(Strict):
    material_id: int = Field(gt=0)
    chunk_id: int = Field(gt=0)
    slide: int | None = Field(default=None, gt=0)
    page: int | None = Field(default=None, gt=0)
    timestamp_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    document_excerpt: bool = False

    @model_validator(mode="after")
    def location(self):
        physical = self.slide is not None or self.page is not None or self.timestamp_seconds is not None
        if self.document_excerpt and physical:
            raise ValueError("A document excerpt cannot invent a physical location.")
        if not physical and not self.document_excerpt:
            raise ValueError("A slide, page, timestamp or document excerpt is required.")
        return self


class Option(Strict):
    id: str = Field(pattern=r"^[A-F]$")
    text: str = Field(min_length=1, max_length=1000)
    explanation: str = Field(min_length=1, max_length=1600)


class Question(Strict):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["multiple_choice", "multiple_select", "short_answer", "numerical"]
    prompt: str = Field(min_length=1, max_length=3000)
    topic: str = Field(min_length=1, max_length=240)
    difficulty: Literal["easy", "standard", "hard"]
    explanation: str = Field(min_length=1, max_length=3000)
    citations: list[Citation] = Field(min_length=1, max_length=6)
    options: list[Option] = Field(default_factory=list, max_length=6)
    correct_option_ids: list[str] = Field(default_factory=list, max_length=6)
    model_answer: str = Field(default="", max_length=3000)
    rubric_keywords: list[str] = Field(default_factory=list, max_length=20)
    value: float | None = None
    unit: str = Field(default="", max_length=25)
    tolerance: float = Field(default=0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid(self):
        if not all(s.strip() for s in [self.prompt, self.topic, self.explanation]):
            raise ValueError("Nonblank question fields required.")
        ids = [o.id for o in self.options]
        if len(ids) != len(set(ids)) or len(
            {o.text.strip().casefold() for o in self.options}
        ) != len(ids):
            raise ValueError("Options must be distinct.")
        if len(set(self.correct_option_ids)) != len(self.correct_option_ids) or any(
            i not in ids for i in self.correct_option_ids
        ):
            raise ValueError("Unknown correct option.")
        if self.kind in ("multiple_choice", "multiple_select"):
            if not 4 <= len(ids) <= 6:
                raise ValueError("Use four to six options.")
            if self.kind == "multiple_choice" and len(self.correct_option_ids) != 1:
                raise ValueError("Choose exactly one correct option.")
            if self.kind == "multiple_select" and not 2 <= len(
                self.correct_option_ids
            ) < len(ids):
                raise ValueError(
                    "Multiple select needs at least two correct options and a distractor."
                )
        elif self.options or self.correct_option_ids:
            raise ValueError("Options apply to choice questions only.")
        if self.kind == "short_answer" and (
            not self.model_answer.strip()
            or not self.rubric_keywords
            or any(not s.strip() for s in self.rubric_keywords)
        ):
            raise ValueError("A short answer needs a model answer and rubric.")
        if self.kind == "numerical":
            import math

            if self.value is None or not math.isfinite(self.value):
                raise ValueError("Finite numerical answer required.")
            unit_info(self.unit)
        return self


class Card(Strict):
    id: str = Field(min_length=1, max_length=80)
    card_type: Literal["term_definition", "question_answer", "cloze"]
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=3000)
    topic: str = Field(min_length=1, max_length=240)
    citations: list[Citation] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def valid(self):
        if not all(v.strip() for v in (self.question, self.answer, self.topic)):
            raise ValueError("Card fields cannot be blank.")
        if self.card_type == "cloze" and "{{c1::" not in self.question:
            raise ValueError("Cloze cards require a c1 deletion.")
        return self


class StudyRequest(BaseModel):
    generation_version: Literal[2] = 2
    course_id: int = Field(gt=0)
    source_id: int | None = Field(default=None, gt=0)
    material_ids: list[StrictInt] = Field(default_factory=list, max_length=5)
    kind: Literal["assessment", "flashcards", "notes"]
    count: StrictInt = Field(default=5, ge=1)
    focus: str = Field(default="", max_length=180)
    difficulty: Literal["easy", "mixed", "hard"] = "mixed"
    type_mix: dict[str, StrictInt] = Field(
        default_factory=lambda: {"multiple_choice": 100}
    )
    scoring: Literal["partial", "all_or_nothing"] = "partial"
    card_type: Literal["term_definition", "question_answer", "cloze"] = (
        "question_answer"
    )
    append_to_deck: str | None = None
    depth: Literal["concise", "standard", "comprehensive"] = "standard"
    style: Literal["outline", "study_guide", "cornell"] = "study_guide"
    include: list[
        Literal["key_terms", "formulas", "worked_examples", "exam_checklist"]
    ] = Field(default_factory=lambda: ["key_terms", "exam_checklist"])

    @model_validator(mode="after")
    def valid(self):
        self.material_ids = sorted(selected_ids(self.source_id, self.material_ids))
        if not self.material_ids:
            raise ValueError("Choose ready material first.")
        if self.source_id is None:
            self.source_id = self.material_ids[0]
        if (
            set(self.type_mix) - set(KINDS)
            or any(type(n) is not int or n < 0 for n in self.type_mix.values())
            or sum(self.type_mix.values()) != 100
        ):
            raise ValueError("Question type percentages must total 100.")
        if self.kind != "notes":
            cap = int(
                os.getenv("MAX_QUESTIONS_PER_REQUEST", "50")
                if self.kind == "assessment"
                else os.getenv("MAX_FLASHCARDS_PER_REQUEST", "100")
            )
            if self.count > cap:
                raise HTTPException(
                    422,
                    {
                        "code": "over_cap",
                        "message": f"Choose at most {cap} items for this request.",
                        "limit": cap,
                    },
                )
        return self


def verified_citations(item, chunks):
    by_id = {int(c["chunk_id"]): c for c in chunks}
    for ref in item.citations:
        actual = by_id.get(ref.chunk_id)
        if not actual or actual["source_id"] != ref.material_id:
            return False
        if ref.document_excerpt:
            if not str(actual.get("source_name", "")).lower().endswith(".docx") or any(actual.get(key) is not None for key in ("slide", "page", "seconds")):
                return False
            continue
        # Physical sources still require the exact supplied location.
        if ref.slide != actual.get("slide") or ref.page != actual.get("page") or ref.timestamp_seconds != actual.get("seconds"):
            return False
        if ref.slide is not None and actual.get("slide") != ref.slide:
            return False
        if ref.page is not None and actual.get("page") != ref.page:
            return False
        if (
            ref.timestamp_seconds is not None
            and actual.get("seconds") != ref.timestamp_seconds
        ):
            return False
    return True


def allocate(total, weights):
    """Largest-remainder integer allocation, deterministic for equal remainders."""
    positive = {k: v for k, v in weights.items() if v > 0}
    if not positive:
        return {}
    denominator = sum(positive.values())
    values = {k: int(total * v / denominator) for k, v in positive.items()}
    remainder = total - sum(values.values())
    for key in sorted(
        positive, key=lambda k: (-(total * positive[k] / denominator - values[k]), k)
    )[:remainder]:
        values[key] += 1
    return values
