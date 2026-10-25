"""Known false acceptances remain rejected even when the model approves them."""

import json
import unittest
from unittest.mock import Mock

from backend.ai.background_review import review_background
from backend.ai.citation_grounding import CitationGrounding
from backend.ai.teaching_checks import background_issues, source_claim_issue
from backend.ai.tutor_sections import tutor_background
from backend.production.demo import SECTIONS
from evaluation.check_background_review import ACCEPT
from evaluation.check_phase2 import FakeLLM

NOTES = SECTIONS[1][1]
ADDED_CLAUSE = (
    "The load factor describes how full the table is, which affects "
    "the likelihood of collisions and the performance of both methods."
)
UNIVERSAL = (
    "Separate chaining simplifies deletion and tolerates higher load factors, "
    "while open addressing offers better cache locality but requires tombstones for deletions."
)
QUALIFIED = (
    "Open addressing often uses tombstones for lazy deletion. Linear probing "
    "can instead reinsert the remaining entries in the affected cluster."
)


class SourceClauseChecks(unittest.TestCase):
    def test_actual_reported_extra_clause_is_not_approved_by_a_positive_model(self):
        client = FakeLLM(supported=True)
        verdict = CitationGrounding(client).verify_claim(ADDED_CLAUSE, NOTES)
        self.assertFalse(verdict["supported"])
        self.assertIn("causal claim", verdict["reason"])
        self.assertEqual(client.calls, [])

    def test_definition_alone_is_still_supported(self):
        result = CitationGrounding(FakeLLM()).verify_claim(
            "A load factor describes how full the table is.", NOTES
        )
        self.assertTrue(result["supported"])

    def test_structured_batch_keeps_definition_and_rejects_added_cause(self):
        result = CitationGrounding(FakeLLM(supported=True)).verify_points(
            [
                {
                    "text": "A load factor describes how full the table is.",
                    "citation_ids": [1],
                },
                {"text": ADDED_CLAUSE, "citation_ids": [1]},
            ],
            [{"content": NOTES}],
        )
        self.assertFalse(result["valid"])
        self.assertEqual([r["supported"] for r in result["results"]], [True, False])

    def test_direct_batch_override_keeps_original_record_ids(self):
        result = CitationGrounding(FakeLLM(supported=True))._verify_batch(
            [
                {"id": 71, "claim": ADDED_CLAUSE, "evidence": "[1] " + NOTES},
                {
                    "id": 83,
                    "claim": "A separate statement to check.",
                    "evidence": "Evidence for the second statement.",
                },
            ]
        )
        self.assertEqual(set(result), {71, 83})
        self.assertFalse(result[71]["supported"])
        self.assertTrue(result[83]["supported"])

    def test_explicit_causal_evidence_is_left_to_semantic_verification(self):
        source = (
            NOTES
            + " Under the stated linear-probing assumptions, higher load factor increases average probe counts."
        )
        self.assertIsNone(source_claim_issue(ADDED_CLAUSE, source))
        source = NOTES + " Higher occupancy can increase the likelihood of collisions."
        self.assertIsNone(source_claim_issue(ADDED_CLAUSE, source))

    def test_plain_paraphrases_and_unrecognised_forms_are_not_claimed_disproved(self):
        self.assertIsNone(
            source_claim_issue("Load factor indicates how full a table is.", NOTES)
        )
        self.assertIsNone(
            source_claim_issue(
                ADDED_CLAUSE,
                "Load factor is N divided by M; further context is required.",
            )
        )


class DeletionClaimChecks(unittest.TestCase):
    def client(self):
        client = Mock()
        client.with_output_budget.return_value = client
        client.generate_json.return_value = ACCEPT
        return client

    def test_reported_universal_claim_is_rejected_without_a_model_vote(self):
        client = self.client()
        review = review_background(
            client, "Compare collision strategies.", NOTES, UNIVERSAL, "standard"
        )
        self.assertFalse(review.acceptable)
        client.generate_json.assert_not_called()

    def test_qualified_negative_and_implementation_scoped_forms_reach_the_reviewer(
        self,
    ):
        for text in [
            QUALIFIED,
            "Open addressing does not require tombstones.",
            "Some open addressing implementations require tombstones for lazy deletion.",
            "This implementation of open addressing requires tombstones.",
            "It is incorrect to say open addressing requires tombstones.",
        ]:
            with self.subTest(text=text):
                self.assertEqual(background_issues(text), [])
                client = self.client()
                self.assertTrue(
                    review_background(
                        client, "Explain deletion.", NOTES, text, "standard"
                    ).acceptable
                )
                client.generate_json.assert_called_once()

    def test_bounded_repair_replaces_universal_claim_without_rewriting_source(self):
        client = self.client()
        client.generate.side_effect = [UNIVERSAL, QUALIFIED]
        result = tutor_background(
            client,
            {"question": "Explain deletion."},
            "MODEL KNOWLEDGE",
            NOTES,
            "standard",
        )
        self.assertEqual(result.text, QUALIFIED)
        self.assertFalse(result.verified)
        self.assertEqual(client.generate.call_count, 2)
        client.generate_json.assert_called_once()
        payload = json.loads(client.generate.call_args.args[0])
        self.assertEqual(payload["checked_source_text"], NOTES)
        self.assertTrue(payload["feedback"]["corrections"])

    def test_unchanged_bad_revision_is_withheld(self):
        client = self.client()
        client.generate.side_effect = [UNIVERSAL, UNIVERSAL]
        result = tutor_background(
            client,
            {"question": "Explain deletion."},
            "MODEL KNOWLEDGE",
            NOTES,
            "standard",
        )
        self.assertIsNone(result)
        self.assertEqual(client.generate.call_count, 2)
        client.generate_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
