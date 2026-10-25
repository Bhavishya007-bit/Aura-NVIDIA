"""Production-only request limits, account flags and durable token revocation."""

import hashlib, os
from datetime import datetime, timezone
from fastapi import HTTPException
from backend.production.config import enabled
from backend.production.limits import db


def is_demo(student):
    if not enabled():
        return False
    with db() as cur:
        cur.execute(
            "SELECT student_id FROM aura_demo_accounts WHERE student_id=%s", (student,)
        )
        return bool(cur.fetchone())


def rate_limit(identity, login=False):
    if not enabled():
        return
    limit = int(
        os.getenv("AURA_LOGIN_PER_MINUTE", "20")
        if login
        else os.getenv("AURA_REQUESTS_PER_MINUTE", "240")
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()
    with db() as cur:
        cur.execute(
            "INSERT INTO aura_request_limits(bucket,minute,requests) VALUES(%s,date_trunc('minute',NOW()),1) ON CONFLICT(bucket,minute) DO UPDATE SET requests=aura_request_limits.requests+1 RETURNING requests",
            (digest,),
        )
        count = cur.fetchone()["requests"]
        cur.execute(
            "DELETE FROM aura_request_limits WHERE minute<NOW()-interval '2 minutes'"
        )
    if count > limit:
        raise HTTPException(
            429,
            {
                "code": "rate_limited",
                "message": "Please wait a moment before trying again.",
            },
            headers={"Retry-After": "60"},
        )


def revoke(token, expires):
    with db() as cur:
        cur.execute("DELETE FROM aura_revoked_tokens WHERE expires_at<NOW()")
        cur.execute(
            "INSERT INTO aura_revoked_tokens(digest,expires_at) VALUES(%s,%s) ON CONFLICT DO NOTHING",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                datetime.fromtimestamp(expires, timezone.utc),
            ),
        )


def revoked(token):
    with db() as cur:
        cur.execute(
            "SELECT digest FROM aura_revoked_tokens WHERE digest=%s AND expires_at>NOW()",
            (hashlib.sha256(token.encode()).hexdigest(),),
        )
        return bool(cur.fetchone())
