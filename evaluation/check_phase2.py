"""Offline regressions: real orchestration/validators with controlled model responses."""
import copy
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from pydantic import ValidationError

from backend.ai.answer_contract import CoverageDecision, AnswerSection, choose_depth
from backend.ai.rag import RAG
from backend.ai.source_aware import SourceAwareTutor
from backend.ai.llm import LLM
from evaluation.evaluate_coverage import metrics
from evaluation.summarize_llm_logs import summarize


def verdict(status="fully_covered", **updates):
    data = {"status": status, "covered_parts": [], "missing_parts": [], "reason": "Fixture evidence.",
            "ambiguous": False, "clarifying_question": None}
    if status in {"fully_covered", "partially_covered"}:
        data["covered_parts"] = [{"part": "membrane structure", "citation_ids": [1]}]
    if status in {"partially_covered", "not_covered"}:
        data["missing_parts"] = ["membrane applications"]
    return {**data, **updates}


def chunk(text="The membrane is a lipid bilayer.", source=7, id="one"):
    return SimpleNamespace(score=0.8, chunk=SimpleNamespace(
        source_id=source, chunk_id=id, content=text, source_name="fixture.pdf", source_type="pdf",
        page=1, slide=None, timestamp_start=None, timestamp_end=None))


class Retriever:
    def __init__(self, rows=None, error=False):
        self.rows = [chunk()] if rows is None else rows
        self.calls = []
        self.error = error

    def _call(self, kind, query=None, **kw):
        self.calls.append((kind, query, kw))
        if self.error:
            raise RuntimeError("database down")
        return self.rows

    def search(self, query, **kw): return self._call("search", query, **kw)
    def concept_context(self, query, **kw): return self._call("concept", query, **kw)
    def overview(self, **kw): return self._call("overview", **kw)


class FakeLLM:
    def __init__(self, decisions=None, sourced="The membrane is a lipid bilayer [1].",
                 beyond="Outside explanation.", supported=True):
        self.decisions = decisions or [verdict()]
        self.sourced, self.beyond, self.supported = sourced, beyond, supported
        self.calls = []
        self.task = "answer"

    def for_task(self, task):
        client = copy.copy(self)
        client.task = task
        return client

    def generate_json(self, data, max_retries=2, system_prompt=None):
        self.calls.append((self.task, "json", system_prompt, data))
        if system_prompt:
            value = self.decisions.pop(0) if len(self.decisions) > 1 else self.decisions[0]
            if isinstance(value, Exception): raise value
            return value
        if "answers_question" in data:
            return {"answers_question": True, "reason": "Relevant fixture."}
        if 'BATCH_CLAIMS_DATA: ' in data:
            items = json.loads(data.split('BATCH_CLAIMS_DATA: ', 1)[1])
            return {'results': [{'id': item['id'], 'supported': self.supported, 'reason': 'Fixture judgement.'}
                                for item in items]}
        if "supported" in data:
            return {"supported": self.supported, "reason": "Fixture judgement."}
        return {"question": "Explain membrane structure."}

    def generate(self, data, max_retries=3, system_prompt=None):
        self.calls.append((self.task, "text", system_prompt, data))
        return self.beyond if "MODEL KNOWLEDGE" in (system_prompt or "") else self.sourced


class PipelineChecks(unittest.TestCase):
    def run_tutor(self, decisions=None, mode="intelligence", rows=None, error=False,
                  question="Explain membrane structure.", depth=None, history=None, **model):
        self.llm = FakeLLM(decisions=decisions, **model)
        self.retriever = Retriever(rows, error)
        rag = RAG(self.retriever, self.llm, source_first_mode=True)
        return SourceAwareTutor(rag, mode, depth).answer(question, course_id=3, source_id=7, history=history)

    def test_full_coverage_reuses_real_citation_validation(self):
        r = self.run_tutor()
        self.assertEqual(r["coverage"]["status"], "fully_covered")
        self.assertEqual(r["coverage"]["retrieval_attempts"], 1)
        self.assertTrue(r["sections"][0]["verified"])
        self.assertEqual(r["sections"][0]["citation_ids"], [1])
        self.assertNotIn("Beyond your material", r["answer"])

    def test_partial_has_separate_provenance(self):
        r = self.run_tutor([verdict("partially_covered")])
        self.assertEqual([s["kind"] for s in r["sections"]], ["sourced", "beyond"])
        self.assertFalse(r["citation_validation"]["valid"])
        self.assertTrue(r["citation_validation"]["source_validation"]["valid"])

    def test_absence_requires_retry_and_stays_passage_scoped(self):
        r = self.run_tutor([verdict("not_covered")])
        self.assertEqual(r["coverage"]["retrieval_attempts"], 2)
        self.assertEqual([s["kind"] for s in r["sections"]], ["beyond"])
        self.assertIn("passages I checked", r["answer"])
        self.assertTrue(any(c[0] == "overview" for c in self.retriever.calls))

    def test_retry_recovers_false_absence(self):
        r = self.run_tutor([verdict("not_covered"), verdict()])
        self.assertEqual(r["coverage"]["status"], "fully_covered")
        self.assertNotIn("couldn't find", r["answer"])

    def test_invalid_judge_id_is_unknown_not_absence(self):
        r = self.run_tutor([verdict(covered_parts=[{"part":"x", "citation_ids":[999]}])])
        self.assertEqual(r["coverage"]["status"], "unknown")

    def test_judge_failure_is_unknown(self):
        r = self.run_tutor([RuntimeError("unavailable")])
        self.assertEqual(r["coverage"]["status"], "unknown")
        self.assertNotIn("couldn't find this", r["answer"])

    def test_empty_retrieval_is_unknown(self):
        r = self.run_tutor(rows=[])
        self.assertEqual(r["coverage"]["status"], "unknown")

    def test_retrieval_failure_is_unknown(self):
        r = self.run_tutor(error=True)
        self.assertEqual(r["coverage"]["status"], "unknown")

    def test_strict_mode_blocks_background(self):
        r = self.run_tutor([verdict("not_covered")], mode="grounded")
        self.assertEqual(r["sections"], [])

    def test_explicit_sources_only_overrides_intelligence(self):
        r = self.run_tutor([verdict("partially_covered")], question="Explain membrane structure. Use only my material.")
        self.assertEqual(r["mode"], "grounded")
        self.assertEqual([s["kind"] for s in r["sections"]], ["sourced"])

    def test_overview_does_not_invent_document_content(self):
        r = self.run_tutor([verdict("not_covered")], question="Summarize this presentation.")
        self.assertTrue(r['sections'])
        self.assertTrue(all(s['kind'] == 'sourced' for s in r['sections']))
        self.assertIn('The membrane is a lipid bilayer.', r['answer'])
        self.assertNotIn('Beyond your material', r['answer'])

    def test_beyond_citations_are_rejected(self):
        r = self.run_tutor([verdict("not_covered")], beyond="Unrelated claim [1].")
        self.assertEqual(r["sections"], [])

    def test_unsupported_sourced_claim_is_not_published(self):
        r = self.run_tutor(sourced="The membrane is made of gold [1].", supported=False)
        self.assertEqual(r["sections"], [])
        self.assertFalse(r["citation_validation"]["valid"])

    def test_clear_question_has_no_clarification(self):
        self.assertIsNone(self.run_tutor()["clarifying_question"])

    def test_ambiguous_prompt_keeps_answer_with_one_question(self):
        r = self.run_tutor([verdict(ambiguous=True, clarifying_question="Do you mean membrane structure?")])
        self.assertTrue(r["sections"])
        self.assertEqual(r["clarifying_question"].count("?"), 1)

    def test_depth_profiles_change_generation_instructions(self):
        self.run_tutor(depth="beginner")
        beginner = next(c[3] for c in self.llm.calls if c[1] == "text")
        self.run_tutor(depth="advanced")
        advanced = next(c[3] for c in self.llm.calls if c[1] == "text")
        self.assertIn("familiar words", beginner)
        self.assertIn("derivations", advanced)

    def test_go_deeper_keeps_last_user_topic(self):
        r = self.run_tutor(question="Go deeper", history=[{"role":"user", "content":"Explain membrane structure."}])
        self.assertEqual(r["depth"], "advanced")
        self.assertIn("membrane", r["retrieval_question"])

    def test_dedup_and_scope_preserved_across_retries(self):
        r = self.run_tutor([verdict("partially_covered")], rows=[chunk(), chunk()])
        self.assertEqual(len(r["sources"]), 1)
        self.assertTrue(all(c[2]["course_id"] == 3 and c[2]["source_id"] == 7 for c in self.retriever.calls))


class ContractChecks(unittest.TestCase):
    def test_inconsistent_decisions_rejected(self):
        for v in [verdict("fully_covered", covered_parts=[]), verdict("not_covered", covered_parts=[{"part":"x","citation_ids":[1]}]),
                  verdict("partially_covered", missing_parts=[]), verdict(clarifying_question="Why?")]:
            with self.subTest(v=v), self.assertRaises(ValidationError): CoverageDecision.model_validate(v)

    def test_multiple_clarifications_rejected(self):
        with self.assertRaises(ValidationError): CoverageDecision.model_validate(verdict(ambiguous=True, clarifying_question="Why? How?"))

    def test_model_knowledge_cannot_claim_verification(self):
        with self.assertRaises(ValidationError): AnswerSection(kind="beyond", text="Background.", provenance="model_knowledge", verified=True)

    def test_depth_current_instruction_precedence(self):
        self.assertEqual(choose_depth("Go deeper", "beginner"), "beginner")

    def test_confusion_matrix_counts_failures(self):
        rows = [{"expected":"fully_covered","predicted":"not_covered","latency_seconds":1},
                {"expected":"partially_covered","predicted":"unknown","latency_seconds":2},
                {"expected":"not_covered","predicted":"not_covered","latency_seconds":3}]
        m = metrics(rows)
        self.assertEqual(m["false_absence_rate"], 0.5)
        self.assertEqual(m["unknown_or_failed_count"], 1)

    def test_cache_missing_usage_not_counted_as_miss(self):
        lines = ["provider=nebius status=success prompt_tokens=100 cached_tokens=50",
                 "provider=nebius status=success prompt_tokens=100 cached_tokens=0",
                 "provider=nebius status=success prompt_tokens=100 cached_tokens=None"]
        m = summarize(lines)
        self.assertEqual(m["request_cache_hit_rate"], 0.5)
        self.assertEqual(m["cache_usage_unknown"], 1)
        self.assertEqual(m["cached_input_token_share"], 0.25)


class ClientChecks(unittest.TestCase):
    def client(self):
        with patch.dict(os.environ, {"NEBIUS_API_KEY":"test-key", "NEBIUS_MODEL":"tested-super", "NEBIUS_COVERAGE_MODEL":"candidate-lightning"}, clear=True):
            return LLM()

    def test_routing_defaults_to_tested_model(self):
        c = self.client()
        self.assertEqual(c.for_task("deep").model_name, "tested-super")

    def test_routing_uses_configured_candidate(self):
        c = self.client()
        with patch.dict(os.environ, {"NEBIUS_COVERAGE_MODEL":"candidate-lightning"}):
            self.assertEqual(c.for_task("coverage").model_name, "candidate-lightning")

    def test_stable_prefix_and_cache_usage_logged(self):
        c = self.client()
        response = Mock(status_code=200)
        response.json.return_value = {"choices":[{"finish_reason":"stop", "message":{"content":"Answer"}}],
            "usage":{"prompt_tokens":100,"completion_tokens":1,"prompt_tokens_details":{"cached_tokens":64}}}
        with patch("backend.ai.llm.requests.post", return_value=response) as post, self.assertLogs("backend.ai.llm", "INFO") as captured:
            self.assertEqual(c.generate("changing question", system_prompt="stable instructions"), "Answer")
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(messages[0], {"role":"system", "content":"stable instructions"})
        self.assertIn("cached_tokens=64 cache_hit=1", captured.output[0])
        self.assertNotIn("test-key", captured.output[0])


if __name__ == "__main__":
    unittest.main()
