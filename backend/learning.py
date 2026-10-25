"""Persistent learner evidence for the active private workspace.

Fixed-parameter BKT prototype, not a calibrated measurement of learning gains.
Only server-graded, source-verified answers are observations. Reading or asking
for an explanation does not change mastery. Diagnostic answers omit learning.
"""

import math
import re
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

PRIOR = 0.20
MODEL_VERSION = "bkt-fixed-v1"


def topic_key(topic: str) -> str:
    # Merge case/spacing variants only. Avoid stemming unrelated scientific terms.
    return " ".join(unicodedata.normalize("NFKC", topic).casefold().split())[:240]


def update_probability(prior: float, correct: bool, question_kind: str, diagnostic=False) -> float:
    if not math.isfinite(prior) or not 0 <= prior <= 1 or type(correct) is not bool:
        raise ValueError("Invalid learner observation.")
    if question_kind not in {"mcq", "multiple_choice", "multiple_select", "short_answer", "numerical"}:
        raise ValueError("Unsupported learner question type.")
    guess = 0.25 if question_kind in {"mcq", "multiple_choice"} else 0.05
    slip = 0.10
    likelihood_known = 1 - slip if correct else slip
    likelihood_unknown = guess if correct else 1 - guess
    denominator = prior * likelihood_known + (1 - prior) * likelihood_unknown
    posterior = prior * likelihood_known / denominator
    learn = 0.0 if diagnostic else 0.10
    return min(0.999, max(0.001, posterior + (1 - posterior) * learn))


def recommended_difficulty(mastery: float, observations: int) -> str:
    if observations < 3 or mastery < 0.40:
        return "beginner"
    if observations < 5 or mastery < 0.75:
        return "intermediate"
    return "advanced"


def lock_learner(cursor, student_id: int, course_id: int) -> None:
    # One transaction lock for this learner/course serializes simultaneous quizzes.
    cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", (student_id, course_id))


def record_result(cursor, student_id: int, artifact_id: str, payload: dict, result: dict, observed_at=None) -> list[dict]:
    """Write evidence and mastery in the SAME transaction as its quiz result.

    Unique question events make retries and historical imports idempotent.
    Callers validate ownership before calling; submitted topics/keys are never used.
    """
    course_id, source_id = payload["course_id"], payload["source_id"]
    mode = payload.get("learning", {}).get("mode", "manual")
    event_kind = mode if mode in {"diagnostic", "conversation"} else "assessment"
    items = {item["id"]: item for item in payload["items"]}
    feedback = result.get("feedback", [])
    if len(feedback) != len(items) or len({entry["question_id"] for entry in feedback}) != len(items):
        raise ValueError("Incomplete learning evidence.")
    lock_learner(cursor, student_id, course_id)
    changed = []
    for entry in feedback:
        item = items.get(entry["question_id"])
        if item is None or type(entry.get("correct")) is not bool:
            raise ValueError("Invalid learning evidence.")
        key = topic_key(item["topic"])
        if not key:
            raise ValueError("Learning evidence needs a topic.")
        cursor.execute(
            """INSERT INTO aura_topic_mastery(student_id, course_id, topic_key, topic)
            VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (student_id, course_id, key, item["topic"].strip()[:240]),
        )
        cursor.execute(
            """SELECT mastery,evidence_count,correct_count FROM aura_topic_mastery
            WHERE student_id=%s AND course_id=%s AND topic_key=%s FOR UPDATE""",
            (student_id, course_id, key),
        )
        observed = cursor.fetchone()
        prior, count, correct_count = (observed['mastery'],observed['evidence_count'],observed['correct_count']) if isinstance(observed,dict) else observed
        posterior = update_probability(prior, entry["correct"], item["kind"], event_kind == "diagnostic")
        cursor.execute(
            """INSERT INTO aura_learning_evidence
            (student_id,course_id,source_id,artifact_id,question_id,topic_key,kind,
             correct,prior_mastery,posterior_mastery,observed_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,NOW()))
            ON CONFLICT DO NOTHING RETURNING question_id""",
            (student_id, course_id, item["citations"][0]["material_id"] if payload.get("generation_version")==2 and item.get("citations") else source_id, str(artifact_id), item["id"], key,
             event_kind, entry["correct"], prior, posterior, observed_at),
        )
        if cursor.fetchone() is None:
            continue
        cursor.execute(
            """UPDATE aura_topic_mastery SET mastery=%s,evidence_count=%s,
            correct_count=%s,updated_at=COALESCE(%s,NOW())
            WHERE student_id=%s AND course_id=%s AND topic_key=%s""",
            (posterior, count + 1, correct_count + int(entry["correct"]), observed_at,
             student_id, course_id, key),
        )
        changed.append({"topic": item["topic"], "before": round(prior, 4),
                        "after": round(posterior, 4), "evidence_count": count + 1})
    return changed


def learner_profile(cursor, student_id: int, course_id: int, source_id=None) -> dict:
    cursor.execute(
        """SELECT m.topic,m.mastery,m.evidence_count,m.correct_count,m.updated_at
        FROM aura_topic_mastery m WHERE m.student_id=%s AND m.course_id=%s
        AND (%s IS NULL OR EXISTS (SELECT 1 FROM aura_learning_evidence e
             WHERE e.student_id=m.student_id AND e.course_id=m.course_id
             AND e.topic_key=m.topic_key AND e.source_id=%s))
        ORDER BY m.mastery,m.topic LIMIT 100""",
        (student_id, course_id, source_id, source_id),
    )
    topics = [{"topic": row[0], "mastery": round(row[1], 4), "evidence_count": row[2],
               "correct_count": row[3], "difficulty": recommended_difficulty(row[1], row[2]),
               "limited_evidence": row[2] < 5,
               "updated_at": row[4].isoformat()} for row in cursor.fetchall()]
    return {"model": MODEL_VERSION, "topics": topics, "diagnostic_recommended": not topics,
            "notice": "Mastery is a model estimate, not a measured learning gain. Limited evidence can give unstable estimates."}


def select_learning_plan(request: Any, profile: dict) -> tuple[Any, dict]:
    mode = request.learning_mode
    if request.kind != "assessment":
        if mode != "manual":
            raise HTTPException(422, "Learning modes apply to assessments only.")
        return request, {}
    if mode == "manual":
        return request, {"mode": mode, "model": MODEL_VERSION, "reason": "Difficulty chosen by you."}
    if mode == "diagnostic":
        return request.model_copy(update={"focus": "", "difficulty": "beginner"}), {
            "mode": mode, "model": MODEL_VERSION,
            "reason": "Sample different supported topics to establish a starting point; untested topics remain unknown."}
    topics = profile["topics"]
    target = None
    if request.focus.strip():
        target = next((row for row in topics if topic_key(row["topic"]) == topic_key(request.focus)), None)
    elif topics:
        target = topics[0]
    focus = request.focus.strip() or (target["topic"] if target else "")
    difficulty = target["difficulty"] if target else "beginner"
    reason = ("Practice the topic with the lowest estimated mastery in this material."
              if target else "No graded evidence for this focus yet; start with beginner questions.")
    update = {"focus": focus[:180], "difficulty": difficulty}
    if mode == "conversation":
        update.update(count=1, question_type="short_answer")
    return request.model_copy(update=update), {"mode": mode, "model": MODEL_VERSION,
        "target_topic": target["topic"] if target else None, "difficulty": difficulty,
        "reason": reason, "evidence_count": target["evidence_count"] if target else 0}


def tutor_style(profile: dict, question: str) -> str:
    words = set(re.findall(r"\w+", question.casefold()))
    matching = [row for row in profile["topics"] if words & set(re.findall(r"\w+", row["topic"].casefold()))]
    if not matching:
        return "Explain unfamiliar terms clearly. Do not assume prior mastery for an untested topic."
    target = min(matching, key=lambda row: row["mastery"])
    if target["difficulty"] == "beginner":
        return "Use an accessible explanation with definitions and small logical steps. Focus on supported relationships."
    if target["difficulty"] == "intermediate":
        return "Explain the supported mechanism and compare related concepts where the evidence permits."
    return "Use precise terminology and supported connections; still explain anything the student asks to clarify."


def initialize_learning(database) -> None:
    with database() as connection:
        with connection.cursor() as cursor:
            # Protect concurrent server startup/migration, then import old graded work.
            cursor.execute("SELECT pg_advisory_xact_lock(817264, 1)")
            cursor.execute(Path(__file__).with_name("learning.sql").read_text(encoding="utf-8"))
            cursor.execute(
                """SELECT a.student_id,a.id,a.payload,r.result,r.completed_at
                FROM aura_study_results r JOIN aura_study_artifacts a ON a.id=r.artifact_id
                JOIN sources s ON s.source_id=a.source_id JOIN courses c ON c.course_id=a.course_id
                WHERE a.kind='assessment' AND r.student_id=a.student_id
                AND s.owner_student_id=a.student_id AND c.owner_student_id=a.student_id
                AND s.course_id=a.course_id
                AND NOT EXISTS (SELECT 1 FROM aura_learning_evidence e WHERE e.artifact_id=a.id)
                ORDER BY r.completed_at,a.id"""
            )
            for student_id, artifact_id, payload, result, completed_at in cursor.fetchall():
                if not result.get("feedback"):
                    continue
                record_result(cursor, student_id, str(artifact_id), payload, result, completed_at)
        connection.commit()


def install_learning(app, database) -> None:
    previous = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        await run_in_threadpool(initialize_learning, database)
        async with previous(application):
            yield
    app.router.lifespan_context = lifespan

