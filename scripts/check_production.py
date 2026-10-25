"""Read-only preflight. It never creates cloud resources or prints secrets."""

import argparse, os, shutil
from pathlib import Path
from dotenv import load_dotenv


def check(path, services=False):
    load_dotenv(path, override=True)
    os.environ["AURA_ENV"] = "production"
    from backend.production.config import validate

    validate()
    print("PASS: Production configuration and secret lengths")
    print(
        "Nebius CLI:",
        (
            "available"
            if shutil.which("nebius")
            else "not installed; cloud trial cannot run here"
        ),
    )
    print(
        "Docker CLI:",
        (
            "available"
            if shutil.which("docker")
            else "not installed; use the CI container build"
        ),
    )
    if not services:
        return
    from backend.auth_db import get_auth_connection

    con = get_auth_connection()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT extname FROM pg_extension WHERE extname='vector'")
            if not cur.fetchone():
                raise RuntimeError(
                    "Enable the vector extension in the managed database."
                )
        print("PASS: PostgreSQL connection and pgvector")
    finally:
        con.close()
    import requests

    endpoint = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
    model = os.getenv("OLLAMA_VISION_MODEL", "").strip()
    if model:
        response = requests.get(
            endpoint + "/api/tags", timeout=10, allow_redirects=False
        )
        response.raise_for_status()
        if model not in {m.get("name") for m in response.json().get("models", [])}:
            raise RuntimeError(
                "The configured vision model is not installed at the vision service."
            )
        print("PASS: Vision model service")
    else:
        print(
            "PENDING: No vision model configured; text tools can run, image/diagram demos cannot."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="deploy/.env.production")
    parser.add_argument("--services", action="store_true")
    args = parser.parse_args()
    if not Path(args.env_file).is_file():
        raise SystemExit(
            "Create deploy/.env.production first with scripts/create_production_config.py."
        )
    try:
        check(args.env_file, args.services)
    except Exception as error:
        if isinstance(error, RuntimeError):
            raise SystemExit(str(error)) from None
        raise SystemExit(
            "Production preflight failed. Check service availability and configuration; no cloud resources were created."
        ) from None
