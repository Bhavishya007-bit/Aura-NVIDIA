"""Controlled checks for source retention and reviewed outside teaching examples."""

import json
import unittest
from unittest.mock import Mock

from backend.ai.answer_contract import CoverageDecision
from backend.ai.rag import RAG
from backend.ai.response_request import response_request
from backend.ai.source_aware import SourceAwareTutor
from backend.ai.tutor_sections import recover_tutor, tutor_background
from backend.production.demo import SECTIONS
from evaluation.check_background_review import ACCEPT, REJECT
from evaluation.check_phase2 import FakeLLM, Retriever, chunk, verdict

QUESTION = "Explain separate chaining and open addressing with an example."
BAD = "Open addressing is also called closed addressing. A load factor below 0.7 bounds probe lengths."
GOOD = "Hypothetical example: h(k) = k mod 10. Keys 12 and 22 both hash to 2. With linear probing, 12 occupies slot 2 and 22 occupies slot 3."


def partial():
    return verdict(
        "partially_covered",
        covered_parts=[
            {
                "part": "Definitions of separate chaining and open addressing",
                "citation_ids": [1],
            }
        ],
        missing_parts=["A worked collision example"],
    )


class TutorSectionChecks(unittest.TestCase):
    def test_demo_definitions_survive_rejected_source_drafts(self):
        notes = SECTIONS[1][1]
        llm = FakeLLM(
            decisions=[partial()],
            sourced="A fabricated performance guarantee [1].",
            supported=False,
            beyond=GOOD,
        )
        result = SourceAwareTutor(RAG(Retriever([chunk(notes)]), llm)).answer(
            QUESTION, course_id=3, source_id=7
        )
        self.assertEqual([s["kind"] for s in result["sections"]], ["sourced", "beyond"])
        self.assertIn(notes, result["sections"][0]["text"])
        self.assertTrue(result["sections"][0]["verified"])
        self.assertEqual(result["sections"][0]["citation_ids"], [1])
        self.assertEqual(result["sections"][1]["text"], GOOD)
        self.assertFalse(result["sections"][1]["verified"])
        self.assertNotIn("fabricated performance", result["answer"])
        self.assertNotIn(
            "couldn't verify a source-backed explanation", result["answer"]
        )
        self.assertIn("exact excerpts", result["answer"])
        self.assertEqual(result["coverage"]["status"], "partially_covered")
        payload = json.loads(
            next(c[3] for c in llm.calls if "MODEL KNOWLEDGE" in (c[2] or ""))
        )
        self.assertIn(notes, payload["checked_source_text"])

    def test_recovery_keeps_only_complete_approved_claims_and_their_ids(self):
        checked = {
            "stage": "grounding",
            "question_validation": {"valid": True},
            "grounding_validation": {
                "results": [
                    {
                        "claim": "Separate chaining stores colliding entries in a collection",
                        "citations": [1],
                        "supported": True,
                    },
                    {
                        "claim": "Every lookup is guaranteed constant time",
                        "citations": [1],
                        "supported": False,
                    },
                    {
                        "claim": "A fake citation makes this claim safe",
                        "citations": [999],
                        "supported": True,
                    },
                ]
            },
        }
        section, validation = recover_tutor(
            [{"content": SECTIONS[1][1]}],
            [checked],
            CoverageDecision.model_validate(partial()),
            QUESTION,
            response_request(QUESTION),
        )
        self.assertIn("Separate chaining", section.text)
        self.assertNotIn("guaranteed", section.text)
        self.assertNotIn("fake", section.text)
        self.assertEqual(section.citation_ids, [1])
        self.assertEqual(validation["response_mode"], "checked_points")

    def test_no_unrelated_source_is_quoted_when_coverage_is_unknown(self):
        section, _ = recover_tutor(
            [{"content": "An unrelated passage about a different topic."}],
            [],
            CoverageDecision(status="unknown", reason="Unavailable"),
            QUESTION,
            response_request(QUESTION),
        )
        self.assertIsNone(section)

    def test_failed_topic_check_cannot_release_a_supported_but_off_topic_draft(self):
        checked = {
            "stage": "grounding",
            "question_validation": {"valid": False},
            "grounding_validation": {
                "results": [
                    {
                        "claim": "The unrelated topic is supported elsewhere",
                        "citations": [1],
                        "supported": True,
                    }
                ]
            },
        }
        section, validation = recover_tutor(
            [{"content": SECTIONS[1][1]}],
            [checked],
            CoverageDecision.model_validate(partial()),
            QUESTION,
            response_request(QUESTION),
        )
        self.assertNotIn("unrelated topic", section.text)
        self.assertEqual(validation["response_mode"], "extractive")

    def background(self, texts, reviews):
        client = Mock()
        client.with_output_budget.return_value = client
        client.generate.side_effect = texts
        client.generate_json.side_effect = reviews
        return client, tutor_background(
            client,
            {"question": QUESTION},
            "MODEL KNOWLEDGE",
            SECTIONS[1][1],
            "standard",
        )

    def test_reported_alias_and_threshold_claim_are_revised_before_publication(self):
        client, section = self.background([BAD, GOOD], [REJECT, ACCEPT])
        self.assertEqual(section.text, GOOD)
        self.assertFalse(section.verified)
        self.assertEqual(client.generate.call_count, 2)
        self.assertEqual(client.generate_json.call_count, 2)
        revised = json.loads(client.generate.call_args.args[0])
        self.assertEqual(revised["prior_draft"], BAD)
        self.assertEqual(revised["feedback"]["corrections"], REJECT["issues"])

    def test_unchanged_rejected_background_is_not_rerolled(self):
        client, section = self.background([BAD, BAD], [REJECT])
        self.assertIsNone(section)
        self.assertEqual(client.generate_json.call_count, 1)

    def test_review_unavailable_or_malformed_withholds_background(self):
        for review in [RuntimeError("unavailable"), {"accurate": True}]:
            with self.subTest(review=type(review).__name__):
                client, section = self.background([GOOD], [review])
                self.assertIsNone(section)
                self.assertEqual(client.generate.call_count, 1)

    def test_document_citation_in_background_is_rejected_before_review(self):
        client, section = self.background([GOOD + " [1]"], [ACCEPT])
        self.assertIsNone(section)
        client.generate_json.assert_not_called()

    def test_rejected_revisions_are_bounded(self):
        client, section = self.background(
            [BAD, "A different incorrect explanation."], [REJECT, REJECT]
        )
        self.assertIsNone(section)
        self.assertEqual(client.generate.call_count, 2)
        self.assertEqual(client.generate_json.call_count, 2)


if __name__ == "__main__":
    unittest.main()
