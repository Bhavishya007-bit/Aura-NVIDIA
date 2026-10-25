"""Authored transport and planning fixtures; never calls a hosted model."""

import asyncio, unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from backend.generation_jobs import GenerationStopped
from backend.study_v2 import provider
from backend.study_v2.contracts import StudyRequest, Card
from backend.study_v2.planning import plan_batches, unique_items
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
        self.assertEqual(target, 3)
        self.assertTrue(notices)
        self.assertEqual({a["kind"] for b in batches for a in b}, {"multiple_choice"})

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
