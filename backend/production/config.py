"""Validate production configuration without printing credentials."""

import os
from urllib.parse import urlsplit
from psycopg2.extensions import parse_dsn


def enabled():
    return os.getenv("AURA_ENV", "local").lower() == "production"


def flag(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def hosts():
    return [
        s.strip()
        for s in os.getenv("AURA_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
        if s.strip()
    ]


def validate():
    if not enabled():
        return
    secret = os.getenv("AUTH_JWT_SECRET", "")
    if len(secret.encode()) < 32 or secret.startswith(("replace_", "change_")):
        raise RuntimeError("Set a random AUTH_JWT_SECRET of at least 32 bytes.")
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("Set DATABASE_URL for the production PostgreSQL database.")
    try:
        values = parse_dsn(url)
    except Exception:
        raise RuntimeError(
            "DATABASE_URL is not a valid PostgreSQL connection string."
        ) from None
    mode = values.get("sslmode") or os.getenv("PGSSLMODE", "require")
    if mode not in ("require", "verify-ca", "verify-full") and not flag(
        "AURA_ALLOW_INSECURE_DATABASE"
    ):
        raise RuntimeError("Production database connections require TLS.")
    mapping = {
        "host": "DB_HOST",
        "port": "DB_PORT",
        "dbname": "DB_NAME",
        "user": "DB_USER",
        "password": "DB_PASSWORD",
        "sslrootcert": "PGSSLROOTCERT",
        "channel_binding": "PGCHANNELBINDING",
    }
    for key, target in mapping.items():
        if key in values:
            os.environ[target] = values[key]
    os.environ["PGSSLMODE"] = mode
    if not os.getenv("NEBIUS_API_KEY") or os.getenv("NEBIUS_API_KEY", "").startswith(
        "replace_"
    ):
        raise RuntimeError("Set the server-side Token Factory API key.")
    if (
        urlsplit(
            os.getenv(
                "NEBIUS_BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1"
            )
        ).scheme
        != "https"
    ):
        raise RuntimeError("Production Token Factory connections require HTTPS.")
    if not hosts() or "*" in hosts():
        raise RuntimeError("Set AURA_ALLOWED_HOSTS to the public hostname.")
    if "*" in os.getenv("AURA_CORS_ORIGINS", ""):
        raise RuntimeError(
            "List explicit production CORS origins, or use the same-origin default."
        )
    for key, default in [
        ("AURA_USER_DAILY_TOKENS", 500000),
        ("AURA_GLOBAL_DAILY_TOKENS", 2000000),
        ("AURA_REQUESTS_PER_MINUTE", 240),
        ("AURA_LOGIN_PER_MINUTE", 20),
    ]:
        try:
            value = int(os.getenv(key, str(default)))
        except ValueError:
            raise RuntimeError(f"{key} must be a positive integer.") from None
        if value < 1:
            raise RuntimeError(f"{key} must be a positive integer.")
    if os.getenv("AURA_CODE_BACKEND", "disabled") == "docker":
        raise RuntimeError(
            "Do not mount the host Docker socket into the public app. Use the isolated Nebius sandbox backend or disable code execution."
        )
    if flag("AURA_DEMO_ENABLED") and (
        len(os.getenv("AURA_DEMO_PASSWORD", "")) < 16
        or os.getenv("AURA_DEMO_PASSWORD", "").startswith("replace_")
    ):
        raise RuntimeError("Set AURA_DEMO_PASSWORD to at least 16 characters.")
