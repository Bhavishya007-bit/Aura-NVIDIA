

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)


def get_auth_connection():
    if os.getenv("DATABASE_URL"):
        return psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10)
    connection = psycopg2.connect(
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=10,
    )
    return connection
