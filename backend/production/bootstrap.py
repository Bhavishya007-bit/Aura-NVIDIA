"""One transaction for empty initialization and additive production migrations."""

import re
from pathlib import Path
from backend.auth_db import get_auth_connection
from scripts.init_database import schema_statements

ROOT = Path(__file__).resolve().parents[2]


def migration(path):
    return re.sub(r"(?m)^\s*(?:BEGIN|COMMIT);\s*$", "", (ROOT / path).read_text())


def bootstrap():
    con = get_auth_connection()
    try:
        with con.cursor() as cur:
            # Transaction-scoped locking also works through managed transaction poolers.
            cur.execute("SELECT pg_advisory_xact_lock(817266,2)")
            cur.execute("SELECT to_regclass('public.students')")
            existing = cur.fetchone()[0]
            if existing is None:
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE')"
                )
                if cur.fetchone()[0]:
                    raise RuntimeError(
                        "The database contains other tables. Use a dedicated empty Aura database; no tables were changed."
                    )
                for sql in schema_statements():
                    cur.execute(sql)
            else:
                for path in ("auth-migration.sql", "backend/private_workspaces.sql"):
                    cur.execute(migration(path))
            for path in (
                "backend/study_tools.sql",
                "backend/material_preferences.sql",
                "backend/learning.sql",
                "backend/study_rhythm.sql",
                "backend/agents/schema.sql",
                "backend/preparation_jobs.sql",
                "backend/production/schema.sql",
            ):
                cur.execute(migration(path))
            from backend.generation_jobs import SCHEMA

            cur.execute(SCHEMA)
            cur.execute(migration("backend/study_v2/schema.sql"))
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
