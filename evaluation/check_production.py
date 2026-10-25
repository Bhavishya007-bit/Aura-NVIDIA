"""Authored production-policy checks. No cloud resources, hosted models or real credentials."""

import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from evaluation import check_study_v2_integration as fixtures
from backend.production import limits, security, config, web


class ConfigChecks(unittest.TestCase):
    def test_local_profile_does_not_require_cloud_settings(self):
        with patch.dict(os.environ, {"AURA_ENV": "local"}, clear=True):
            config.validate()
            self.assertIsNone(limits.reserve({}))

    def test_production_rejects_weak_secrets_and_non_tls_database(self):
        env = {
            "AURA_ENV": "production",
            "AUTH_JWT_SECRET": "short",
            "DATABASE_URL": "postgresql://user:synthetic@db.example/aura?sslmode=require",
            "NEBIUS_API_KEY": "synthetic",
            "AURA_ALLOWED_HOSTS": "aura.example.org",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "AUTH_JWT_SECRET"):
                config.validate()
            os.environ["AUTH_JWT_SECRET"] = "s" * 48
            config.validate()
            self.assertEqual(os.environ["DB_HOST"], "db.example")
            os.environ["DATABASE_URL"] = (
                "postgresql://user:synthetic@db.example/aura?sslmode=disable"
            )
            with self.assertRaisesRegex(RuntimeError, "TLS"):
                config.validate()

    def test_public_container_cannot_mount_host_docker_backend(self):
        env = {
            "AURA_ENV": "production",
            "AUTH_JWT_SECRET": "s" * 48,
            "DATABASE_URL": "postgresql://u:p@db.example/aura?sslmode=require",
            "NEBIUS_API_KEY": "synthetic",
            "AURA_ALLOWED_HOSTS": "aura.example.org",
            "AURA_CODE_BACKEND": "docker",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Docker socket"):
                config.validate()

    def test_smoke_rejects_non_https_public_urls_and_url_credentials(self):
        from scripts.smoke_public import smoke

        for url in (
            "http://aura.example.org",
            "https://user:password@aura.example.org",
            "https://aura.example.org?token=secret",
        ):
            with self.assertRaises(ValueError):
                smoke(url)

    def test_logout_still_revokes_when_request_profile_is_cached(self):
        from backend import auth_routes

        app = FastAPI()
        app.include_router(auth_routes.router)

        @app.middleware("http")
        async def cached(request, call_next):
            request.state.production_student = {"student_id": 42}
            return await call_next(request)

        revoked = []
        with patch.object(
            auth_routes, "is_token_revoked", return_value=False
        ), patch.object(
            auth_routes, "decode_access_token", return_value={"sub": "42"}
        ), patch.object(
            auth_routes, "revoke_token", side_effect=revoked.append
        ):
            response = TestClient(app).post(
                "/auth/logout", headers={"Authorization": "Bearer authored-token"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(revoked, ["authored-token"])
        self.assertEqual(response.json()["message"], "Logout successful.")

    def test_bootstrap_refuses_an_unrelated_nonempty_database(self):
        from backend.production import bootstrap

        class Cursor:
            sql = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql):
                self.sql.append(sql)

            def fetchone(self):
                return (None,) if "to_regclass" in self.sql[-1] else (True,)

        class Connection:
            committed = False
            rolled_back = False

            def cursor(self):
                return Cursor()

            def commit(self):
                self.committed = True

            def rollback(self):
                self.rolled_back = True

            def close(self):
                pass

        connection = Connection()
        with patch.object(bootstrap, "get_auth_connection", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "dedicated empty"):
                bootstrap.bootstrap()
        self.assertTrue(connection.rolled_back)
        self.assertFalse(connection.committed)
        self.assertFalse(any("CREATE TABLE" in s for s in Cursor.sql))
        self.assertIn("pg_advisory_xact_lock", Cursor.sql[0])


@unittest.skipUnless(
    os.getenv("AURA_PGLITE_MODULE"), "Optional PostgreSQL engine not configured"
)
class ProductionPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.StudyV2Postgres.setUpClass.__func__(cls)
        cls.bridge.query(Path("backend/production/schema.sql").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.bridge.close()

    def setUp(self):
        fixtures.StudyV2Postgres.setUp(self)
        self.bridge.query(
            "DELETE FROM aura_production_usage;DELETE FROM aura_request_limits;DELETE FROM aura_revoked_tokens;UPDATE aura_deployment_control SET ai_enabled=TRUE;"
        )
        self.stack.enter_context(patch.object(limits, "db", self.db))
        self.stack.enter_context(patch.object(security, "db", self.db))
        self.stack.enter_context(patch.object(web, "db", self.db))
        self.stack.enter_context(
            patch.dict(
                os.environ,
                {
                    "AURA_ENV": "production",
                    "AURA_AI_ENABLED": "true",
                    "AURA_USER_DAILY_TOKENS": "300",
                    "AURA_GLOBAL_DAILY_TOKENS": "1000",
                    "AURA_REQUESTS_PER_MINUTE": "60",
                    "AURA_LOGIN_PER_MINUTE": "20",
                    "AURA_ALLOWED_HOSTS": "testserver",
                },
            )
        )

    def test_per_user_budget_release_and_actual_usage(self):
        token = limits.actor.set(42)
        try:
            reservation = limits.reserve({"messages": [], "max_tokens": 100})
            with self.assertRaises(Exception) as error:
                limits.reserve({"messages": [], "max_tokens": 250})
            self.assertEqual(error.exception.status_code, 429)
            limits.settle(reservation, {"prompt_tokens": 10, "completion_tokens": 5})
        finally:
            limits.actor.reset(token)
        rows = self.bridge.query("SELECT * FROM aura_production_usage ORDER BY account")
        self.assertEqual([r["used_tokens"] for r in rows], [15, 15])
        self.assertEqual([r["reserved_tokens"] for r in rows], [0, 0])

    def test_global_cap_covers_different_users(self):
        with patch.dict(os.environ, {"AURA_GLOBAL_DAILY_TOKENS": "120"}):
            token = limits.actor.set(42)
            try:
                first = limits.reserve({"messages": [], "max_tokens": 70})
            finally:
                limits.actor.reset(token)
            token = limits.actor.set(43)
            try:
                with self.assertRaises(Exception) as error:
                    limits.reserve({"messages": [], "max_tokens": 60})
                self.assertEqual(error.exception.status_code, 429)
            finally:
                limits.actor.reset(token)
            limits.settle(first, {})
        rows = self.bridge.query(
            "SELECT used_tokens FROM aura_production_usage WHERE account=0"
        )
        self.assertGreater(rows[0]["used_tokens"], 70)

    def test_kill_switch_blocks_generation_without_hiding_saved_work(self):
        self.bridge.query("UPDATE aura_deployment_control SET ai_enabled=FALSE")
        with self.assertRaises(Exception) as error:
            limits.check_enabled()
        self.assertEqual(error.exception.status_code, 503)
        client = self.web_client()
        self.assertEqual(
            client.get(
                "/api/study/saved", headers={"Authorization": "Bearer synthetic"}
            ).status_code,
            200,
        )
        self.assertEqual(
            client.post(
                "/api/study/tools",
                headers={"Authorization": "Bearer synthetic"},
                json={},
            ).status_code,
            503,
        )

    def test_rate_limits_and_durable_hashed_revocation(self):
        with patch.dict(os.environ, {"AURA_LOGIN_PER_MINUTE": "2"}):
            security.rate_limit("authored-client", True)
            security.rate_limit("authored-client", True)
            with self.assertRaises(Exception) as error:
                security.rate_limit("authored-client", True)
            self.assertEqual(error.exception.status_code, 429)
        security.revoke("authored-token", 2000000000)
        self.assertTrue(security.revoked("authored-token"))
        self.assertFalse(security.revoked("another-token"))
        self.assertNotEqual(
            self.bridge.query("SELECT digest FROM aura_revoked_tokens")[0]["digest"],
            "authored-token",
        )

    def web_client(self, demo=False):
        app = FastAPI()

        @app.get("/health")
        def health():
            return {"status": "ok"}

        @app.get("/auth/me")
        def profile():
            return {"name": "Synthetic learner"}

        @app.get("/study/saved")
        def saved():
            return {"items": []}

        @app.post("/study/tools")
        def create():
            return {"ok": True}

        @app.post("/courses/3/preparation-jobs")
        def upload():
            return {"ok": True}

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        Path(directory.name, "index.html").write_text("<html>Aura sign-in</html>")
        with patch(
            "backend.auth_routes.get_current_student",
            return_value={"student_id": 42, "is_demo": demo},
        ):
            wrapped = web.install(app, directory.name)
        return TestClient(wrapped)

    def test_fresh_session_spa_api_prefix_and_no_anonymous_data(self):
        client = self.web_client()
        self.assertEqual(client.get("/").status_code, 200)
        self.assertIn("Aura sign-in", client.get("/login").text)
        self.assertEqual(client.get("/api/auth/me").status_code, 401)
        self.assertEqual(client.get("/api/study/saved").status_code, 401)
        self.assertEqual(client.get("/api/ready").status_code, 200)
        response = client.get(
            "/api/study/unknown", headers={"Authorization": "Bearer synthetic"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("<html>", response.text)
        self.assertEqual(client.get("/").headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(
            client.get("/", headers={"host": "untrusted.example"}).status_code, 400
        )

    def test_shared_demo_rejects_private_file_uploads(self):
        client = self.web_client(True)
        self.assertEqual(
            client.post(
                "/api/courses/3/preparation-jobs",
                headers={"Authorization": "Bearer synthetic"},
            ).status_code,
            403,
        )

    def test_demo_seed_is_idempotent_and_does_not_replace_a_personal_account(self):
        from backend.production import demo
        from evaluation.check_agents import SQLCursor

        bridge = self.bridge
        bridge.query(
            "ALTER TABLE students ADD COLUMN IF NOT EXISTS name text;ALTER TABLE students ADD COLUMN IF NOT EXISTS email text;ALTER TABLE students ADD COLUMN IF NOT EXISTS password_hash text;CREATE SEQUENCE IF NOT EXISTS demo_student_ids START 100;ALTER TABLE students ALTER COLUMN student_id SET DEFAULT nextval('demo_student_ids');ALTER TABLE courses ADD COLUMN IF NOT EXISTS course_name text;CREATE SEQUENCE IF NOT EXISTS demo_course_ids START 100;ALTER TABLE courses ALTER COLUMN course_id SET DEFAULT nextval('demo_course_ids');CREATE UNIQUE INDEX IF NOT EXISTS demo_course_owner ON courses(owner_student_id);DROP TABLE aura_preparation_jobs;"
        )
        bridge.query(Path("backend/preparation_jobs.sql").read_text())

        class Connection:
            def __init__(self):
                bridge.query("BEGIN")

            def cursor(self):
                class TupleCursor(SQLCursor):
                    def fetchone(self):
                        row = super().fetchone()
                        return tuple(row.values()) if row else None

                return TupleCursor(bridge)

            def commit(self):
                bridge.query("COMMIT")

            def rollback(self):
                bridge.query("ROLLBACK")

            def close(self):
                pass

        env = {
            "AURA_DEMO_ENABLED": "true",
            "AURA_DEMO_PASSWORD": "authored-demo-password-for-test",
            "AURA_DEMO_EMAIL": "judge@aura.example.org",
        }
        with patch.object(demo, "get_auth_connection", Connection), patch.dict(
            os.environ, env
        ):
            demo.seed_demo()
            demo.seed_demo()
            self.assertEqual(
                bridge.query("SELECT count(*) AS n FROM aura_demo_accounts")[0]["n"], 1
            )
            jobs = bridge.query("SELECT * FROM aura_preparation_jobs")
            self.assertEqual(len(jobs), 1)
            import pymupdf

            with pymupdf.open(jobs[0]["staged_path"]) as pdf:
                self.assertEqual(len(pdf), 6)
                self.assertIn("synthetic", pdf[-1].get_text())
            Path(jobs[0]["staged_path"]).unlink(missing_ok=True)
            bridge.query(
                "UPDATE students SET email='personal@example.org' WHERE student_id=42"
            )
            os.environ["AURA_DEMO_EMAIL"] = "personal@example.org"
            with self.assertRaisesRegex(RuntimeError, "non-demo"):
                demo.seed_demo()
