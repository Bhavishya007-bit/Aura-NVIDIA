"""Serialize daily reservations across concurrent batches and server workers."""

import os
from fastapi import HTTPException
from backend.generation_jobs import db, current


def reserve(tokens, student=None):
    job = current.get() or ((None, student) if student is not None else None)
    if not job:
        return None
    cap = int(os.getenv("STUDY_DAILY_TOKEN_BUDGET", "1000000"))
    with db() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s,817265)", (job[1],))
        cur.execute(
            "INSERT INTO aura_daily_token_budget(student_id,day) VALUES(%s,CURRENT_DATE) ON CONFLICT DO NOTHING",
            (job[1],),
        )
        cur.execute(
            "SELECT * FROM aura_daily_token_budget WHERE student_id=%s AND day=CURRENT_DATE FOR UPDATE",
            (job[1],),
        )
        row = cur.fetchone()
        if row["used_tokens"] + row["reserved_tokens"] + tokens > cap:
            raise HTTPException(
                429,
                {
                    "code": "daily_token_budget",
                    "message": "Your daily study-generation allowance is used. Try again after the daily allowance resets.",
                },
            )
        cur.execute(
            "UPDATE aura_daily_token_budget SET reserved_tokens=reserved_tokens+%s WHERE student_id=%s AND day=CURRENT_DATE RETURNING day",
            (tokens, job[1]),
        )
        return (job[1], str(cur.fetchone()["day"]), tokens)


def settle(reservation, usage):
    if reservation is None:
        return
    student, day, reserved = reservation
    # Missing terminal usage on cancellation is charged conservatively to the
    # quota, separately from provider-reported usage displayed in metrics.
    charge = (
        (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
        if usage
        else reserved
    )
    with db() as cur:
        cur.execute(
            "UPDATE aura_daily_token_budget SET reserved_tokens=GREATEST(0,reserved_tokens-%s),used_tokens=used_tokens+%s WHERE student_id=%s AND day=%s",
            (reserved, charge, student, day),
        )
