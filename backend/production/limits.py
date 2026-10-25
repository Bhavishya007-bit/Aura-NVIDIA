"""Cross-worker token reservations and an operator-controlled AI kill switch."""

import contextvars, json, os
from contextlib import contextmanager
from psycopg2.extras import RealDictCursor
from fastapi import HTTPException
from backend.auth_db import get_auth_connection
from backend.production.config import enabled, flag

actor = contextvars.ContextVar("aura_production_actor", default=None)


@contextmanager
def db():
    con = get_auth_connection()
    try:
        with con.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def check_enabled(cur=None):
    if not enabled():
        return
    if not flag("AURA_AI_ENABLED", True):
        raise HTTPException(
            503,
            {
                "code": "ai_paused",
                "message": "AI generation is temporarily paused. Your saved work is still available.",
            },
        )
    if cur is None:
        with db() as cursor:
            return check_enabled(cursor)
    cur.execute("SELECT ai_enabled FROM aura_deployment_control WHERE id=1")
    row = cur.fetchone()
    if not row or not row["ai_enabled"]:
        raise HTTPException(
            503,
            {
                "code": "ai_paused",
                "message": "AI generation is temporarily paused. Your saved work is still available.",
            },
        )


def reserve(payload):
    if not enabled():
        return None
    student = actor.get()
    if student is None:
        from backend.generation_jobs import current

        job = current.get()
        student = job[1] if job else None
    if not student:
        raise HTTPException(
            503,
            {
                "code": "unscoped_generation",
                "message": "Sign in again before starting AI generation.",
            },
        )
    maximum = int(payload.get("max_tokens", 4096))
    # A byte-based upper-bound reservation avoids exceeding budgets on a long prompt.
    tokens = (
        len(json.dumps(payload.get("messages", []), ensure_ascii=False).encode())
        + maximum
    )
    with db() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(817266,1)")
        check_enabled(cur)
        for account, limit in [
            (0, int(os.getenv("AURA_GLOBAL_DAILY_TOKENS", "2000000"))),
            (student, int(os.getenv("AURA_USER_DAILY_TOKENS", "500000"))),
        ]:
            cur.execute(
                "INSERT INTO aura_production_usage(day,account) VALUES(CURRENT_DATE,%s) ON CONFLICT DO NOTHING",
                (account,),
            )
            cur.execute(
                "SELECT day,used_tokens,reserved_tokens FROM aura_production_usage WHERE day=CURRENT_DATE AND account=%s FOR UPDATE",
                (account,),
            )
            row = cur.fetchone()
            if row["used_tokens"] + row["reserved_tokens"] + tokens > limit:
                raise HTTPException(
                    429,
                    {
                        "code": "daily_ai_limit",
                        "message": "The daily AI allowance has been reached. Saved work remains available. Please try again after the daily reset.",
                    },
                )
        cur.execute(
            "UPDATE aura_production_usage SET reserved_tokens=reserved_tokens+%s WHERE day=CURRENT_DATE AND account IN (0,%s) RETURNING day",
            (tokens, student),
        )
        return (student, str(cur.fetchone()["day"])[:10], tokens)


def settle(reservation, usage):
    if reservation is None:
        return
    student, day, reserved = reservation
    values = [usage.get("prompt_tokens"), usage.get("completion_tokens")]
    actual = sum(values) if all(type(v) is int and v >= 0 for v in values) else reserved
    with db() as cur:
        cur.execute(
            "UPDATE aura_production_usage SET reserved_tokens=GREATEST(0,reserved_tokens-%s),used_tokens=used_tokens+%s WHERE day=%s AND account IN (0,%s)",
            (reserved, actual, day, student),
        )
