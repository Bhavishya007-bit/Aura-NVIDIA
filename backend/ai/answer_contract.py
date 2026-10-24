"""Versioned source-aware answer contract, independent of models and databases."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Coverage = Literal["fully_covered", "partially_covered", "not_covered", "unknown"]
Depth = Literal["beginner", "standard", "advanced"]
Mode = Literal["grounded", "intelligence"]
CITATIONS = re.compile(r"\[(\d+)\]|【(\d+)】")
NONCANONICAL_CITATIONS = re.compile(r'(?:\[\s*\d+(?:\s*[,;–-]\s*\d+)+\s*\]|【\s*\d+(?:\s*[,;–-]\s*\d+)+\s*】)')


def has_noncanonical_citations(text: str) -> bool:
    """Reject ambiguous numeric reference groups in prose without guessing IDs.

    Numeric arrays in inline/fenced code remain data. Document references must
    use [1][2], with IDs checked against their explicit citation metadata.
    """
    fence = None
    for line in text.splitlines():
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if marker:
            token, suffix = marker.groups()
            if fence is None:
                fence = token[0], len(token)
            elif token[0] == fence[0] and len(token) >= fence[1] and not suffix.strip():
                fence = None
            continue
        if fence is None:
            prose = re.sub(r'(`+).*?\1', '', line)
            if NONCANONICAL_CITATIONS.search(prose):
                return True
    return False


def citation_ids(text: str) -> list[int]:
    return list(dict.fromkeys(int(a or b) for a, b in CITATIONS.findall(text)))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CoveredPart(StrictModel):
    part: str = Field(min_length=1, max_length=1000)
    citation_ids: list[int] = Field(min_length=1, max_length=96)


class CoverageDecision(StrictModel):
    status: Coverage
    covered_parts: list[CoveredPart] = Field(default_factory=list, max_length=12)
    missing_parts: list[str] = Field(default_factory=list, max_length=12)
    reason: str = Field(min_length=1, max_length=1000)
    ambiguous: bool = False
    clarifying_question: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "fully_covered" and (not self.covered_parts or self.missing_parts):
            raise ValueError("Full coverage requires evidence for all requested parts.")
        if self.status == "partially_covered" and (not self.covered_parts or not self.missing_parts):
            raise ValueError("Partial coverage needs both covered and missing parts.")
        if self.status == "not_covered" and (self.covered_parts or not self.missing_parts):
            raise ValueError("No coverage cannot contain covered parts.")
        if self.status == "unknown" and self.covered_parts:
            raise ValueError("An unavailable coverage check cannot approve evidence.")
        if any(not item.strip() or len(item) > 1000 for item in self.missing_parts):
            raise ValueError("Missing parts must be short, nonempty descriptions.")
        if self.clarifying_question and (not self.ambiguous or self.clarifying_question.count("?") > 1):
            raise ValueError("Only an ambiguous question may get one clarification.")
        return self

    def check_citations(self, source_count: int):
        if any(type(number) is not int or not 1 <= number <= source_count
               for part in self.covered_parts for number in part.citation_ids):
            raise ValueError("Coverage refers to nonexistent evidence.")
        return self


class AnswerSection(StrictModel):
    kind: Literal["sourced", "beyond"]
    text: str = Field(min_length=1)
    provenance: Literal["uploaded_material", "model_knowledge"]
    verified: bool
    citation_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def honest_provenance(self):
        if has_noncanonical_citations(self.text):
            raise ValueError('Numeric citation groups in prose require canonical references.')
        actual = citation_ids(self.text)
        if self.kind == "beyond":
            if actual or self.citation_ids or self.verified or self.provenance != "model_knowledge":
                raise ValueError("Model background cannot claim document evidence or verification.")
        elif (not actual or actual != self.citation_ids or not self.verified
              or self.provenance != "uploaded_material"):
            raise ValueError("A sourced section needs verified, matching citations.")
        return self


class CoverageReport(CoverageDecision):
    scope: Literal["retrieved_passages"] = "retrieved_passages"
    retrieval_attempts: int = Field(ge=1, le=2)


class SourceAwareFields(StrictModel):
    response_schema_version: Literal["aura-answer-v1"] = "aura-answer-v1"
    coverage: CoverageReport
    sections: list[AnswerSection]
    mode: Mode
    depth: Depth
    clarifying_question: str | None = None
    follow_up_options: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def consistent_output(self):
        if self.mode == "grounded" and any(s.kind == "beyond" for s in self.sections):
            raise ValueError("Grounded mode cannot publish background.")
        if self.clarifying_question and (not self.sections or not self.coverage.ambiguous
                                        or self.clarifying_question != self.coverage.clarifying_question):
            raise ValueError("Clarification requires an answer and a matching ambiguity decision.")
        return self


def choose_depth(question: str, requested: Depth | None = None) -> Depth:
    # One answer's depth is not silently promoted to a durable memory preference.
    if requested:
        return requested
    if re.search(r"\b(beginner|simply|simpler|simple terms|step by step|eli5)\b", question, re.I):
        return "beginner"
    if re.search(r"\b(advanced|go deeper|in depth|technical detail|derive|derivation)\b", question, re.I):
        return "advanced"
    return "standard"
