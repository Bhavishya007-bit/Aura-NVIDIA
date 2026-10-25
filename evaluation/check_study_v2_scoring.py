import unittest
from pydantic import ValidationError
from fastapi import HTTPException
from backend.study_v2.contracts import (
    Question,
    StudyRequest,
    allocate,
    verified_citations,
)
from backend.study_v2.scoring import score


def question(kind="multiple_select"):
    return Question(
        id="q1",
        kind=kind,
        prompt="Select the supported statements",
        topic="Membranes",
        difficulty="easy",
        explanation="The material supports A and C.",
        citations=[{"material_id": 7, "chunk_id": 1, "page": 2}],
        options=[
            {"id": i, "text": "Statement " + i, "explanation": "Explanation " + i}
            for i in "ABCD"
        ],
        correct_option_ids=["A", "C"] if kind == "multiple_select" else ["A"],
    )


class ScoringChecks(unittest.TestCase):
    def test_multiple_select_partial_penalty_and_clamp(self):
        q = question()
        self.assertEqual(score(q, ["A"])["score"], 0.5)
        self.assertEqual(score(q, ["A", "C"])["score"], 1)
        self.assertEqual(score(q, ["A", "B"])["score"], 0)
        self.assertEqual(score(q, ["B", "D"])["score"], 0)
        self.assertEqual(score(q, [])["score"], 0)
        self.assertEqual(len(score(q, ["A"])["options"]), 4)

    def test_all_or_nothing_and_single_choice(self):
        self.assertEqual(score(question(), ["A"], "all_or_nothing")["score"], 0)
        self.assertEqual(score(question(), ["C", "A"], "all_or_nothing")["score"], 1)
        self.assertEqual(score(question("multiple_choice"), "A")["score"], 1)
        self.assertEqual(score(question("multiple_choice"), "B")["score"], 0)
        for invalid in (["A", "A"], ["G"], ["A", "B"]):
            with self.assertRaises(ValueError):
                score(question("multiple_choice"), invalid)

    def test_schema_rejects_missing_correct_answers_and_fake_citations(self):
        raw = question().model_dump()
        raw["correct_option_ids"] = ["A"]
        with self.assertRaises(ValidationError):
            Question.model_validate(raw)
        self.assertTrue(
            verified_citations(question(), [{"chunk_id": 1, "source_id": 7, "page": 2}])
        )
        self.assertFalse(
            verified_citations(question(), [{"chunk_id": 1, "source_id": 8, "page": 2}])
        )
        self.assertFalse(
            verified_citations(question(), [{"chunk_id": 1, "source_id": 7, "page": 3}])
        )

    def test_short_answer_keywords_before_borderline_judge(self):
        raw = question().model_dump()
        raw.update(
            kind="short_answer",
            options=[],
            correct_option_ids=[],
            model_answer="Lipids form a bilayer.",
            rubric_keywords=["lipids", "bilayer"],
        )
        q = Question.model_validate(raw)
        called = []
        judge = lambda data: called.append(data) or {"correct": False}
        self.assertEqual(
            score(q, "A bilayer is formed by lipids", judge=judge)["score"], 1
        )
        self.assertEqual(called, [])
        self.assertEqual(
            score(q, "Lipids never form a bilayer", judge=judge)["score"], 0
        )
        self.assertEqual(len(called), 1)

    def test_numeric_units_tolerance_and_no_execution(self):
        raw = question().model_dump()
        raw.update(
            kind="numerical",
            options=[],
            correct_option_ids=[],
            value=2.0,
            unit="m",
            tolerance=0.01,
        )
        q = Question.model_validate(raw)
        self.assertEqual(score(q, "200 cm")["score"], 1)
        self.assertEqual(score(q, "2 s")["score"], 0)
        self.assertEqual(score(q, '__import__("os")')["score"], 0)

    def test_caps_and_balanced_rounding(self):
        with self.assertRaises(HTTPException):
            StudyRequest(course_id=3, source_id=7, kind="assessment", count=51)
        self.assertEqual(
            StudyRequest(
                course_id=3, material_ids=[9, 7], kind="flashcards", count=100
            ).material_ids,
            [7, 9],
        )
        self.assertEqual(
            sum(allocate(7, {"a": 40, "b": 20, "c": 20, "d": 20}).values()), 7
        )
        with self.assertRaises(ValidationError):
            StudyRequest(
                course_id=3,
                source_id=7,
                kind="assessment",
                type_mix={"multiple_choice": 50},
            )
