"""Check local dependencies, schema and Ollama without loading embedding weights."""
import importlib.util
from pathlib import Path
import sys

from dotenv import dotenv_values
import psycopg2
import requests

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    failures = []
    settings = dotenv_values(ROOT / "backend/.env")
    for key in ["DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "AUTH_JWT_SECRET"]:
        value = settings.get(key)
        if not value or value.startswith("replace_"):
            failures.append(f"Configure {key} in backend/.env.")
    for module in ["fastapi", "uvicorn", "multipart", "pgvector", "jwt", "pwdlib", "email_validator",
                   "requests", "sentence_transformers", "torch", "faster_whisper", "av", "pymupdf",
                   "pptx", "docx", "rapidocr_onnxruntime"]:
        if importlib.util.find_spec(module) is None:
            failures.append(f"Missing Python module: {module}. Install requirements.txt in this interpreter.")
    if not failures:
        connection = None
        try:
            connection = psycopg2.connect(dbname=settings["DB_NAME"], user=settings["DB_USER"],
                password=settings["DB_PASSWORD"], host=settings["DB_HOST"], port=settings["DB_PORT"], connect_timeout=5)
            with connection.cursor() as cursor:
                cursor.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
                if cursor.fetchone() is None: failures.append("The vector extension is missing.")
                cursor.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public'")
                columns = set(cursor.fetchall())
                required = {('students','password_hash'),('courses','owner_student_id'),('sources','owner_student_id'),
                            ('chunks','embedding'),('aura_study_artifacts','payload'),('aura_study_results','result'),
                            ('aura_material_preferences','archived')}
                for table, column in sorted(required - columns):
                    failures.append(f"Missing database column: {table}.{column}.")
            if not failures: print("OK: local database, pgvector, authentication and study schema.")
        except psycopg2.Error:
            failures.append("Could not connect to the database. Check the database service and backend/.env.")
        finally:
            if connection is not None: connection.close()
    base = (settings.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip('/')
    base = base.removesuffix('/api/chat')
    model = settings.get('OLLAMA_MODEL') or 'qwen2.5:3b'
    try:
        response = requests.get(base + '/api/tags', timeout=5)
        response.raise_for_status()
        names = {entry['name'] for entry in response.json().get('models', []) if 'name' in entry}
        if model not in names:
            failures.append(f"Ollama model is missing: run ollama pull {model}.")
        else: print("OK: Ollama is reachable and the configured model is installed.")
    except (requests.RequestException, ValueError, TypeError):
        failures.append("Ollama is unreachable or returned an invalid response. Start Ollama and retry.")
    for message in failures: print("CHECK:", message)
    if not failures:
        print("Ready to start backend.main:app. Embedding weights download on first indexing; preload them before a demo.")
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
