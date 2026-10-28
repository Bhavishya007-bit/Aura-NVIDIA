"""Authored transport and planning fixtures; never calls a hosted model."""

import asyncio, unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from backend.generation_jobs import GenerationStopped
from backend.study_v2 import provider
from backend.study_v2.contracts import StudyRequest, Card
from backend.study_v2.planning import plan_batches, refill_batches, unique_items
from evaluation.study_generation_metrics import summarize


class RuntimeChecks(unittest.IsolatedAsyncioTestCase):
    async def test_stop_closes_inflight_stream_and_settles_reservation(self):
        started = asyncio.Event()
        closed = []
        settled = []

        class Response:
            def raise_for_status(self):
                pass

            async def aiter_lines(self):
                started.set()
                await asyncio.Event().wait()
                yield ""

        class Stream:
            async def __aenter__(self):
                return Response()

            async def __aexit__(self, *args):
                closed.append(True)

        class Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def stream(self, *args, **kwargs):
                return Stream()

        llm = SimpleNamespace(
            model_name="configured-role",
            reasoning_effort=None,
            api_key="synthetic",
            read_timeout=30,
            base_url="https://invalid.example",
            json_max_tokens=100,
        )
        llm.for_task = lambda _: llm
        llm.for_summary = lambda: llm
        llm.with_output_budget = lambda *args, **kw: llm
        calls = []

        def guard():
            calls.append(True)
            if started.is_set():
                raise GenerationStopped()

        with patch.object(provider, "LLM", return_value=llm), patch.object(
            provider.httpx, "AsyncClient", Client
        ), patch.object(provider, "guard", guard), patch.object(
            provider, "reserve", return_value=("reservation",)
        ), patch.object(
            provider, "settle", side_effect=lambda *args: settled.append(args)
        ), patch.object(
            provider, "add_usage"
        ):
            with self.assertRaises(GenerationStopped):
                await asyncio.wait_for(provider.complete({}, {}, "flashcards"), 2)
        self.assertTrue(closed)
        self.assertTrue(settled)
        self.assertGreaterEqual(len(calls), 1)


class RecoveryChecks(unittest.IsolatedAsyncioTestCase):
    async def run_generation(self, accept=True):
        from backend.study_v2 import engine
        request = StudyRequest(course_id=3, source_id=7, kind="assessment", count=20)
        data = {"heuristic": "fixture", "concepts": [{"topic": f"Topic {n}", "material_id": 7, "chunk_ids": [1]} for n in range(7)], "numerical_supported": False}
        chunks = [{"chunk_id":1,"source_id":7,"source_name":"Fixture.pdf","content":"Authored event facts.","page":1,"slide":None,"seconds":None}]
        calls=[]
        async def complete(context, instructions, kind):
            if "checks" in instructions["task"]:
                return {"checks":[{"id":i["id"],"supported":True} for i in instructions["items"]]}
            calls.append(instructions)
            if not accept: return {"items":[]}
            return {"items":[{"id":f"candidate-{len(calls)}","kind":"multiple_choice","prompt":f"Distinct learning objective {len(calls)}?","topic":"Events","difficulty":instructions["allocation"][0]["difficulty"],"explanation":"The supplied event facts support this answer.","citations":[{"material_id":7,"chunk_id":1,"page":1}],"options":[{"id":"A","text":"Correct","explanation":"Supported"},{"id":"B","text":"Incorrect","explanation":"Contradicted"},{"id":"C","text":"Unrelated","explanation":"Not supported"},{"id":"D","text":"Another distractor","explanation":"Not supported"}],"correct_option_ids":["A"]}]}
        def persist(request,items,chunks,notices,*args): return {"items":list(items),"notices":list(notices)}
        with patch.object(engine,"outline",return_value=(data,chunks)), patch.object(engine,"complete",side_effect=complete), patch.object(engine,"persist",side_effect=persist), patch.object(engine,"guard"), patch.object(engine,"unique_items",side_effect=lambda produced,old,embed:produced):
            if not accept:
                with self.assertRaises(ValueError): await engine.batches(request,42,lambda texts:[])
                return calls
            result=await engine.batches(request,42,lambda texts:[])
            return result,calls

    async def test_recovers_twenty_items_past_old_three_round_limit(self):
        result,calls=await self.run_generation()
        self.assertEqual(len(result["items"]),20)
        self.assertEqual(len(calls),20)
        self.assertFalse(result["notices"])

    async def test_three_stalled_rounds_stop_without_padding(self):
        calls=await self.run_generation(accept=False)
        self.assertEqual(len(calls),12)  # Four small batches, three zero-progress rounds.


class PlanningChecks(unittest.TestCase):
    def test_numeric_allocations_only_use_material_with_formula(self):
        data = {
            "heuristic": "Authored capacity fixture",
            "concepts": [
                {"topic": "Words", "material_id": 7, "chunk_ids": [1]},
                {"topic": "Distance", "material_id": 9, "chunk_ids": [2]},
            ],
            "numerical_supported": True,
            "numerical_materials": [9],
        }
        request = StudyRequest(
            course_id=3,
            material_ids=[7, 9],
            kind="assessment",
            count=6,
            type_mix={"multiple_choice": 50, "numerical": 50},
        )
        batches, target, notices = plan_batches(request, data)
        self.assertEqual(target, 6)
        self.assertTrue(
            all(
                a["concept"]["material_id"] == 9
                for batch in batches
                for a in batch
                if a["kind"] == "numerical"
            )
        )
        self.assertEqual(
            sum(a["kind"] == "numerical" for batch in batches for a in batch), 3
        )

    def test_unsupported_numerics_are_redistributed_not_fabricated(self):
        data = {
            "heuristic": "Authored capacity fixture",
            "concepts": [{"topic": "Words", "material_id": 7, "chunk_ids": [1]}],
            "numerical_supported": False,
        }
        request = StudyRequest(
            course_id=3,
            source_id=7,
            kind="assessment",
            count=5,
            type_mix={"numerical": 100},
        )
        batches, target, notices = plan_batches(request, data)
        self.assertEqual(target, 5)
        self.assertTrue(notices)
        self.assertEqual({a["kind"] for b in batches for a in b}, {"multiple_choice"})

    def test_estimated_capacity_is_not_a_request_ceiling(self):
        data = {"heuristic": "fixture", "concepts": [{"topic": "Events", "material_id": 7, "chunk_ids": [1]}], "numerical_supported": False}
        request = StudyRequest(course_id=3, source_id=7, kind="assessment", count=20)
        batches, target, _ = plan_batches(request, data)
        self.assertEqual(target, 20)
        self.assertEqual(sum(map(len, batches)), 20)
        self.assertTrue(all(len(b) <= 5 for b in batches))
        self.assertGreater(len({a["angle"] for b in batches for a in b}), 1)

    def test_refill_rotates_sources_and_preserves_missing_types(self):
        data = {"heuristic": "fixture", "concepts": [{"topic": f"Topic {n}", "material_id": 7, "chunk_ids": [n]} for n in range(1, 8)], "numerical_supported": False}
        request = StudyRequest(course_id=3, source_id=7, kind="assessment", count=4, type_mix={"multiple_choice": 50, "short_answer": 50})
        batches, _, _ = plan_batches(request, data)
        original = [a for b in batches for a in b]
        retry = [a for b in refill_batches(request, data, original, [SimpleNamespace(kind="multiple_choice")], 1) for a in b]
        self.assertEqual(len(retry), 3)
        self.assertEqual(sum(a["kind"] == "multiple_choice" for a in retry), 1)
        self.assertEqual(sum(a["kind"] == "short_answer" for a in retry), 2)
        self.assertNotEqual(retry[0]["concept"], original[0]["concept"])

    def test_hash_and_cosine_dedup(self):
        def card(text):
            return Card(
                id=text,
                card_type="question_answer",
                question=text,
                answer="Answer",
                topic="Topic",
                citations=[{"material_id": 7, "chunk_id": 1, "page": 2}],
            )

        old = card("What is a membrane?")
        same = card("WHAT is a membrane!")
        near = card("Define a membrane")
        distinct = card("What is ATP?")

        def vectors(texts):
            return [[0, 1] if "ATP" in t else [1, 0] for t in texts]

        self.assertEqual(
            [c.question for c in unique_items([same, near, distinct], [old], vectors)],
            ["What is ATP?"],
        )

    def test_metrics_do_not_invent_unmeasured_accuracy(self):
        data = summarize([])
        self.assertIsNone(data["schema_valid_rate"])
        self.assertIsNone(data["prompt_tokens"])
        measured = summarize(
            [
                {
                    "raw": 10,
                    "valid": 8,
                    "cited": 6,
                    "supported": 4,
                    "duplicates": 1,
                    "latency": 2,
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                }
            ]
        )
        self.assertEqual(measured["schema_valid_rate"], 0.8)
        self.assertEqual(measured["citation_validity_rate"], 0.75)
        self.assertEqual(measured["duplicate_rate"], 0.25)
