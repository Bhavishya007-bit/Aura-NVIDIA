"""Synthetic PostgreSQL/API and batch tests; no hosted model, user DB or real embeddings."""

import asyncio, json, os, unittest
from datetime import date, datetime
from contextlib import contextmanager, ExitStack
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.auth_routes import get_current_student
from backend.agents.store import Store
from backend import generation_jobs as jobs
from backend.study_v2 import engine, planning, product, budget, provider, progress
from backend.study_v2.contracts import StudyRequest
from evaluation.check_agents import SQLBridge, SQLCursor


class DateCursor(SQLCursor):
    def execute(self, sql, params=()):
        return super().execute(
            sql,
            tuple(
                v.isoformat() if isinstance(v, (date, datetime)) else v for v in params
            ),
        )


def embeddings(texts):
    vocabulary = {text: i for i, text in enumerate(sorted(set(texts)))}
    return [
        [float(i == vocabulary[text]) for i in range(len(vocabulary))] for text in texts
    ]


@unittest.skipUnless(
    os.getenv("AURA_PGLITE_MODULE"), "Optional PostgreSQL engine not configured"
)
class StudyV2Postgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = SQLBridge()
        query = cls.bridge.query
        cls.bridge.query = lambda sql, params=None: query(
            sql,
            (
                None
                if params is None
                else tuple(
                    v.isoformat() if isinstance(v, (date, datetime)) else v
                    for v in params
                )
            ),
        )
        cls.bridge.query(
            """CREATE TABLE students(student_id integer PRIMARY KEY);
          CREATE TABLE courses(course_id integer PRIMARY KEY,owner_student_id integer);
          CREATE TABLE sources(source_id integer PRIMARY KEY,course_id integer,owner_student_id integer,source_name text,source_type text,status text,metadata jsonb DEFAULT '{}');
          CREATE TABLE chunks(chunk_id integer PRIMARY KEY,source_id integer,content text,page_number integer,slide_number integer,timestamp_seconds real,topic_id integer);
          CREATE TABLE aura_material_preferences(student_id integer,source_id integer,archived boolean DEFAULT FALSE,PRIMARY KEY(student_id,source_id));
          CREATE TABLE aura_preparation_jobs(source_id integer,state text);
          INSERT INTO students VALUES(42),(43); INSERT INTO courses VALUES(3,42),(4,43);
          INSERT INTO sources(source_id,course_id,owner_student_id,source_name,source_type,status) VALUES(7,3,42,'Membranes.pdf','pdf','success'),(9,3,42,'Transcript.pdf','pdf','success'),(8,4,43,'Private.pdf','pdf','success');
          INSERT INTO chunks VALUES(1,7,'Membranes contain a lipid bilayer. Integral proteins interact with its hydrophobic core.',2,NULL,NULL,NULL),
          (2,9,'Channels transport selected solutes across a membrane.',3,NULL,NULL,NULL),(3,8,'Other account private content',1,NULL,NULL,NULL);"""
        )
        for path in (
            "backend/study_tools.sql",
            "backend/agents/schema.sql",
            "backend/learning.sql",
            "backend/study_rhythm.sql",
        ):
            cls.bridge.query(Path(path).read_text())
        cls.bridge.query(jobs.SCHEMA)
        cls.bridge.query(Path("backend/study_v2/schema.sql").read_text())
        cls.bridge.query(Path("backend/study_v2/schema.sql").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.bridge.close()

    def setUp(self):
        self.bridge.query(
            """DELETE FROM aura_learning_evidence;DELETE FROM aura_topic_mastery;DELETE FROM aura_study_attempts;
          DELETE FROM aura_card_reviews;DELETE FROM aura_generation_metrics;DELETE FROM aura_generation_jobs;DELETE FROM aura_study_results;
          DELETE FROM aura_study_artifacts;DELETE FROM aura_concept_outlines;DELETE FROM aura_study_activity;DELETE FROM aura_daily_token_budget;
          DELETE FROM aura_material_preferences;DELETE FROM aura_agent_tasks;DELETE FROM aura_agent_runs;"""
        )
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

        @contextmanager
        def db():
            with self.bridge.lock:
                self.bridge.query("BEGIN")
                try:
                    yield DateCursor(self.bridge)
                    self.bridge.query("COMMIT")
                except BaseException:
                    self.bridge.query("ROLLBACK")
                    raise

        self.db = db
        for module in (jobs, engine, planning, product, budget, provider):
            self.stack.enter_context(patch.object(module, "db", db))
        store = Store(connect=self.bridge.connect)
        self.stack.enter_context(patch.object(product, "Store", return_value=store))
        self.stack.enter_context(patch.object(progress, "Store", return_value=store))
        self.stack.enter_context(patch.dict(os.environ, {"NEBIUS_API_KEY": ""}))
        app = FastAPI()
        app.dependency_overrides[get_current_student] = lambda: {"student_id": 42}
        jobs.install_generation(
            app,
            {
                "generate": (
                    StudyRequest.model_validate,
                    lambda data, student: engine.generate(data, student, embeddings),
                )
            },
        )
        product.install(app)
        self.client = TestClient(app)
        self.serial = 0

    def job(self, kind="flashcards", count=8, **settings):
        payload = StudyRequest(
            course_id=3,
            source_id=7,
            material_ids=[7, 9],
            kind=kind,
            count=count,
            **settings,
        ).model_dump()
        response = self.client.post(
            "/study/generation-jobs",
            json={"course_id": 3, "operation": "generate", "payload": payload},
        )
        self.assertEqual(response.status_code, 202, response.text)
        value = response.json()
        self.bridge.query(
            "UPDATE aura_generation_jobs SET state='running' WHERE id=$1", [value["id"]]
        )
        return value, payload

    async def model(self, context, instructions, kind):
        if instructions.get("task", "").startswith("Check every"):
            return {
                "checks": [
                    {"id": i["id"], "supported": True} for i in instructions["items"]
                ]
            }
        if instructions.get("task", "").startswith("Check these notes"):
            return {"supported": True}
        if kind == "notes":
            section = instructions["section"]
            chunk = instructions["evidence"][0]
            return {
                "id": section["id"],
                "title": section["title"],
                "text": "These authored study notes explain the supported membrane facts in this particular section.",
                "citations": [
                    {
                        "material_id": chunk["source_id"],
                        "chunk_id": chunk["chunk_id"],
                        "page": chunk["page"],
                    }
                ],
                "_provider_usage": {"prompt_tokens": 10, "completion_tokens": 20},
                "_provider_model": "configured-role",
            }
        items = []
        for allocation in instructions["allocation"]:
            self.serial += 1
            c = allocation["concept"]
            chunk = next(
                e for e in instructions["evidence"] if e["chunk_id"] in c["chunk_ids"]
            )
            cite = {
                "material_id": chunk["source_id"],
                "chunk_id": chunk["chunk_id"],
                "page": chunk["page"],
            }
            if kind == "flashcards":
                items.append(
                    {
                        "id": f"authored-{self.serial}",
                        "card_type": "question_answer",
                        "question": f'Authored card {self.serial} about {c["topic"]}',
                        "answer": "Source-supported answer.",
                        "topic": c["topic"],
                        "citations": [cite],
                    }
                )
            else:
                items.append(
                    {
                        "id": f"authored-{self.serial}",
                        "kind": allocation["kind"],
                        "prompt": f"Authored question {self.serial} about the source",
                        "topic": c["topic"],
                        "difficulty": allocation["difficulty"],
                        "explanation": "The cited material supports the correct statement.",
                        "citations": [cite],
                        "options": [
                            {
                                "id": i,
                                "text": "Statement " + i,
                                "explanation": "Reason " + i,
                            }
                            for i in "ABCD"
                        ],
                        "correct_option_ids": (
                            ["A", "C"]
                            if allocation["kind"] == "multiple_select"
                            else ["A"]
                        ),
                    }
                )
        return {"items": items}

    def generate(self, kind="flashcards", count=8, **settings):
        job, data = self.job(kind, count, **settings)
        token = jobs.current.set((job["id"], 42))
        try:
            with patch.object(engine, "complete", self.model):
                result = engine.generate(data, {"student_id": 42}, embeddings)
        finally:
            jobs.current.reset(token)
        return result, job

    def test_outline_cache_capacity_and_owner_isolation(self):
        one = self.client.get(
            "/study/capacity?course_id=3&kind=assessment&material_ids=7&material_ids=9"
        )
        self.assertEqual(one.status_code, 200, one.text)
        self.assertEqual(one.json()["max_supported"], 6)
        two = self.client.get(
            "/study/capacity?course_id=3&kind=flashcards&material_ids=9&material_ids=7"
        )
        self.assertEqual(two.json()["max_supported"], 8)
        self.assertEqual(
            len(self.bridge.query("SELECT * FROM aura_concept_outlines")), 1
        )
        self.assertEqual(
            self.client.get(
                "/study/capacity?course_id=3&kind=assessment&material_ids=8"
            ).status_code,
            404,
        )

    def test_caps_and_one_active_job_have_friendly_codes(self):
        self.job()
        payload = StudyRequest(
            course_id=3, source_id=7, kind="assessment", count=5
        ).model_dump()
        response = self.client.post(
            "/study/generation-jobs",
            json={"course_id": 3, "operation": "generate", "payload": payload},
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"]["code"], "one_job_at_a_time")
        payload["count"] = 51
        response = self.client.post(
            "/study/generation-jobs",
            json={"course_id": 3, "operation": "generate", "payload": payload},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "over_cap")

    def test_batched_capacity_shortfall_and_answer_key_redaction(self):
        result, job = self.generate("assessment", 50)
        self.assertEqual(len(result["payload"]["items"]), 6)
        self.assertTrue(result["payload"]["fulfillment"]["partial"])
        self.assertIn("supports about 6", result["payload"]["notice"])
        self.assertNotIn("correct_option_ids", result["payload"]["items"][0])
        self.assertNotIn("explanation", result["payload"]["items"][0]["options"][0])
        row = self.bridge.query("SELECT * FROM aura_study_artifacts")[0]
        self.assertIn("correct_option_ids", row["payload"]["items"][0])
        self.assertEqual(
            {c["source_id"] for c in result["payload"]["citations"]}, {7, 9}
        )

    def test_append_keeps_card_review_due_fields(self):
        first, job = self.generate()
        card = first["payload"]["items"][0]["id"]
        self.bridge.query("UPDATE aura_generation_jobs SET state='completed'")
        self.bridge.query(
            "UPDATE aura_card_reviews SET interval_days=17,repetitions=4 WHERE card_id=$1",
            [card],
        )
        second, _ = self.generate(count=4, append_to_deck=first["id"])
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(len(second["payload"]["items"]), 12)
        review = self.bridge.query(
            "SELECT interval_days,repetitions FROM aura_card_reviews WHERE card_id=$1",
            [card],
        )[0]
        self.assertEqual(review, {"interval_days": 17, "repetitions": 4})

    def test_cancelled_generation_keeps_partial_and_blocks_further_writes(self):
        result, job = self.generate(count=4)
        response = self.client.post(
            f"/study/generation-jobs/{job['id']}/cancel?course_id=3"
        )
        self.assertEqual(response.json()["state"], "cancelling")
        token = jobs.current.set((job["id"], 42))
        try:
            with self.assertRaises(jobs.GenerationStopped):
                jobs.guard()
        finally:
            jobs.current.reset(token)
        self.assertEqual(
            len(
                self.bridge.query("SELECT payload FROM aura_study_artifacts")[0][
                    "payload"
                ]["items"]
            ),
            4,
        )

    def test_section_notes_and_optimistic_editing(self):
        from backend.study_v2 import notes

        job, data = self.job("notes")
        token = jobs.current.set((job["id"], 42))
        try:
            with patch.object(notes, "complete", self.model):
                result = engine.generate(data, {"student_id": 42}, embeddings)
        finally:
            jobs.current.reset(token)
        self.assertEqual(result["payload"]["coverage"]["covered"], 2)
        self.assertEqual(result["payload"]["coverage"]["missing_sections"], [])
        sections = [
            {"id": i["id"], "text": "Edited by learner"}
            for i in result["payload"]["items"]
        ]
        saved = self.client.patch(
            "/study/notes/" + result["id"], json={"revision": 0, "sections": sections}
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()["payload"]["user_edited"])
        self.assertEqual(
            self.client.patch(
                "/study/notes/" + result["id"],
                json={"revision": 0, "sections": sections},
            ).status_code,
            409,
        )

    def test_saved_multiple_select_attempt_and_real_progress(self):
        result, _ = self.generate("assessment", 2, type_mix={"multiple_select": 100})
        created = self.client.post(
            "/study/attempts", json={"artifact_id": result["id"], "scoring": "partial"}
        )
        self.assertEqual(created.status_code, 201, created.text)
        attempt = created.json()
        token = attempt["resume_token"]
        answers = {q["id"]: ["A"] for q in result["payload"]["items"]}
        saved = self.client.patch(
            "/study/attempts/" + attempt["id"],
            json={
                "resume_token": token,
                "revision": 0,
                "answers": answers,
                "position": 1,
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        read = self.client.get(
            "/study/attempts/" + attempt["id"], headers={"X-Aura-Resume-Token": token}
        )
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(read.json()["answers"], answers)
        submitted = self.client.post(
            "/study/attempts/" + attempt["id"] + "/submit",
            json={
                "resume_token": token,
                "revision": 1,
                "answers": answers,
                "position": 1,
            },
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["score"], 50)
        self.assertEqual(submitted.json()["feedback"][0]["options"][0]["correct"], True)
        summary = self.client.get("/study/progress/summary?course_id=3&range=all")
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["quiz_average"], 50)
        self.assertIsNotNone(summary.json()["overall_mastery"])

    def test_material_rename_delete_and_foreign_access(self):
        result = self.client.patch(
            "/study/materials/7/name", json={"course_id": 3, "name": "Lecture notes"}
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["name"], "Lecture notes.pdf")
        self.assertEqual(
            self.client.patch(
                "/study/materials/8/name", json={"course_id": 3, "name": "No"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/study/materials/7/delete?course_id=3").status_code, 200
        )
        visible = self.client.get("/study/materials/managed?course_id=3")
        self.assertNotIn(7, [r["source_id"] for r in visible.json()["sources"]])

    def test_daily_budget_reservations_are_released_and_isolated(self):
        with patch.dict(os.environ, {"STUDY_DAILY_TOKEN_BUDGET": "100"}):
            reservation = budget.reserve(80, 42)
            with self.assertRaises(Exception) as error:
                budget.reserve(30, 42)
            self.assertEqual(error.exception.status_code, 429)
            other = budget.reserve(30, 43)
            budget.settle(reservation, {"prompt_tokens": 10, "completion_tokens": 5})
            budget.settle(other, {})
        rows = self.bridge.query(
            "SELECT student_id,used_tokens,reserved_tokens FROM aura_daily_token_budget ORDER BY student_id"
        )
        self.assertEqual(rows[0]["used_tokens"], 15)
        self.assertEqual(rows[0]["reserved_tokens"], 0)
        self.assertEqual(rows[1]["used_tokens"], 30)

    def test_topups_are_bounded_and_invalid_citations_never_escape(self):
        job, data = self.job("flashcards", 4)
        token = jobs.current.set((job["id"], 42))
        calls = []

        async def invalid(context, instructions, kind):
            calls.append(True)
            output = await self.model(context, instructions, kind)
            for item in output.get("items", []):
                item["citations"][0]["material_id"] = 8
            return output

        try:
            with patch.object(engine, "complete", invalid):
                with self.assertRaises(ValueError):
                    engine.generate(data, {"student_id": 42}, embeddings)
        finally:
            jobs.current.reset(token)
        self.assertEqual(len(calls), 3)
        self.assertEqual(
            self.bridge.query("SELECT count(*) AS n FROM aura_study_artifacts")[0]["n"],
            0,
        )

    def test_missing_note_section_is_retried_once(self):
        from backend.study_v2 import notes

        job, data = self.job("notes")
        token = jobs.current.set((job["id"], 42))
        calls = []

        async def model(context, instructions, kind):
            if kind == "notes":
                calls.append(instructions["section"]["material_id"])
                if instructions["section"]["material_id"] == 9:
                    raise ValueError("Authored invalid section")
            return await self.model(context, instructions, kind)

        try:
            with patch.object(notes, "complete", model):
                value = engine.generate(data, {"student_id": 42}, embeddings)
        finally:
            jobs.current.reset(token)
        self.assertEqual(calls.count(7), 1)
        self.assertEqual(calls.count(9), 2)
        self.assertEqual(value["payload"]["coverage"]["covered"], 1)
        self.assertEqual(value["payload"]["coverage"]["total"], 2)

    def test_paginated_plans_archive_and_dated_tasks(self):
        from psycopg2.extras import Json

        identifiers = [str(uuid4()) for _ in range(8)]
        for i, run_id in enumerate(identifiers):
            self.bridge.query(
                "INSERT INTO aura_agent_runs(id,student_id,course_id,source_id,request,state,created_at) VALUES($1,42,3,7,$2,'completed',NOW()-($3||' hours')::interval)",
                [run_id, {"goal": f"Review topic {i}", "skill": "study_plan"}, str(i)],
            )
        first = self.client.get("/agents/plans?course_id=3&limit=5").json()
        self.assertEqual(first["current"]["id"], identifiers[0])
        self.assertEqual(len(first["items"]), 5)
        second = self.client.get(
            "/agents/plans?course_id=3&limit=5&cursor=" + first["next_cursor"]
        ).json()
        self.assertEqual(len(second["items"]), 2)
        archived = self.client.patch(
            f"/agents/runs/{identifiers[1]}/archive?course_id=3",
            json={"archived": True},
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        filtered = self.client.get("/agents/plans?course_id=3&q=topic%202").json()
        self.assertEqual([r["id"] for r in filtered["items"]], [identifiers[2]])
        task_id = str(uuid4())
        self.bridge.query(
            "INSERT INTO aura_agent_tasks(id,student_id,course_id,title,dedup_key) VALUES($1,42,3,'Review membrane','unique')",
            [task_id],
        )
        moved = self.client.patch(
            f"/agents/tasks/{task_id}/date?course_id=3",
            json={"scheduled_for": "2026-10-24"},
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(
            len(
                self.client.get(
                    "/agents/tasks/by-date?course_id=3&day=2026-10-24"
                ).json()["items"]
            ),
            1,
        )
        self.assertEqual(
            len(
                self.client.get(
                    "/agents/tasks/by-date?course_id=3&day=2026-10-25"
                ).json()["items"]
            ),
            0,
        )
        self.bridge.query(
            "UPDATE aura_agent_tasks SET done=TRUE,completed_at='2026-10-24T12:00:00Z' WHERE id=$1",
            [task_id],
        )
        week = self.client.get("/agents/tasks/week?course_id=3&end=2026-10-24").json()[
            "days"
        ]
        self.assertEqual(len(week), 7)
        self.assertEqual(week[-1]["completed"], 1)
        self.assertEqual(self.client.get("/agents/plans?course_id=4").status_code, 404)

    def test_existing_generation_route_accepts_optional_v2_job_settings(self):
        from backend.study_tools import router

        self.client.app.include_router(router)
        response = self.client.post(
            "/study/tools",
            json={
                "course_id": 3,
                "source_id": 7,
                "material_ids": [7, 9],
                "kind": "flashcards",
                "generation": {"count": 100, "card_type": "cloze"},
            },
        )
        self.assertEqual(response.status_code, 202, response.text)
        row = response.json()
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["requested"], 100)
