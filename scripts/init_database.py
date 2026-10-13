"""Initialize a NEW empty Aura database atomically. Never alter an existing setup."""
import re
from pathlib import Path

import psycopg2
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SQL_FILES = [
    "database/schema.sql", "auth-migration.sql", "backend/private_workspaces.sql",
    "backend/study_tools.sql", "backend/material_preferences.sql", "backend/learning.sql",
]


def schema_statements() -> list[str]:
    # The connection owns one transaction. Remove only the migrations' standalone
    # transaction boundaries, preserving PL/pgSQL DO-block BEGIN/END statements.
    return [re.sub(r"(?m)^\s*(?:BEGIN|COMMIT);\s*$", "", (ROOT / name).read_text(encoding="utf-8"))
            for name in SQL_FILES]


def initialize(connection) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE')")
            row = cursor.fetchone()
            if row is None or row[0]:
                raise RuntimeError("Database is not empty. Initialization refused; existing data was not changed.")
            for sql in schema_statements():
                cursor.execute(sql)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def main() -> None:
    settings = dotenv_values(ROOT / "backend/.env")
    required = ["DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"]
    if any(not settings.get(key) for key in required):
        raise SystemExit("Configure backend/.env first. Run scripts/create_local_config.py for a fresh local setup.")
    connection = None
    try:
        connection = psycopg2.connect(dbname=settings["DB_NAME"], user=settings["DB_USER"],
            password=settings["DB_PASSWORD"], host=settings["DB_HOST"], port=settings["DB_PORT"])
        initialize(connection)
        print("Initialized Aura schema, authentication, private workspaces, study tools and archive preferences.")
    except (psycopg2.Error, RuntimeError) as error:
        if isinstance(error, RuntimeError):
            raise SystemExit(str(error)) from None
        raise SystemExit("Database setup failed. Check database connectivity and the installed pgvector extension package. No setup changes were committed.") from None
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
