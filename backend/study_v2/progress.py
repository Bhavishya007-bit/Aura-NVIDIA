"""Progress summaries are derived only from saved practice, reviews and activity."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.auth_routes import get_current_student
from backend.agents.store import Store
from backend.study_v2.product import safe, instant


def summarize(topics, events, cards_due, period="7d", zone="UTC", now=None):
    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(zone)
    today = now.astimezone(tz).date()
    cutoff = (
        None if period == "all" else now - timedelta(days=7 if period == "7d" else 30)
    )
    eligible = [e for e in events if not cutoff or instant(e["created_at"]) >= cutoff]
    scores = [
        float(e["result"]["score"])
        for e in eligible
        if e.get("kind") == "quiz"
        and isinstance(e.get("result"), dict)
        and isinstance(e["result"].get("score"), (int, float))
    ]
    days = {instant(e["created_at"]).astimezone(tz).date() for e in events}
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    monday = today - timedelta(days=today.weekday())
    durations = [
        e["duration_seconds"]
        for e in events
        if e.get("duration_seconds", 0) > 0
        and instant(e["created_at"]).astimezone(tz).date() >= monday
    ]
    measured = [t for t in topics if t["evidence_count"] > 0]
    mastery = (
        round(sum(t["mastery"] for t in measured) / len(measured) * 100)
        if measured
        else None
    )
    history = {name: [] for name in ("Today", "Yesterday", "2 days ago", "Earlier")}
    for e in eligible:
        age = (today - instant(e["created_at"]).astimezone(tz).date()).days
        bucket = (
            "Today"
            if age <= 0
            else "Yesterday" if age == 1 else "2 days ago" if age == 2 else "Earlier"
        )
        history[bucket].append(e)
    next_topic = min(measured, key=lambda t: t["mastery"]) if measured else None
    return {
        "range": period,
        "scope": "course",
        "overall_mastery": mastery,
        "study_streak": streak,
        "quiz_average": round(sum(scores) / len(scores), 1) if scores else None,
        "time_this_week_seconds": sum(durations) if durations else None,
        "cards_due": cards_due,
        "topics": measured,
        "recommended_next": (
            {
                "topic": next_topic["topic"],
                "mastery": round(next_topic["mastery"] * 100),
                "reason": "Your lowest measured topic mastery.",
            }
            if next_topic
            else None
        ),
        "quizzes": [e for e in eligible if e.get("kind") == "quiz"],
        "history": [{"label": key, "items": values} for key, values in history.items()],
        "notice": "Mastery is an estimate from checked answers, not a measured learning gain. Time includes explicitly recorded sessions only.",
    }


def install(app):
    router = APIRouter()
    store = Store()

    @router.get("/study/progress/summary")
    def progress(
        course_id: int,
        range: str = Query(default="7d", pattern="^(7d|30d|all)$"),
        timezone_name: str = "UTC",
        student=Depends(get_current_student),
    ):
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, "Choose a valid timezone.")
        with store.cursor(student["student_id"], course_id) as cur:
            cur.execute(
                """SELECT topic,mastery,evidence_count,updated_at AS last_practiced_at FROM aura_topic_mastery
                WHERE student_id=%s AND course_id=%s ORDER BY mastery,topic""",
                (student["student_id"], course_id),
            )
            topics = [safe(r) for r in cur.fetchall()]
            cur.execute(
                """SELECT id,kind,title,result,duration_seconds,created_at FROM aura_study_activity
                WHERE student_id=%s AND course_id=%s ORDER BY created_at DESC LIMIT 2000""",
                (student["student_id"], course_id),
            )
            events = [safe(r) for r in cur.fetchall()]
            cur.execute(
                """SELECT a.id,a.payload,r.result,r.completed_at FROM aura_study_artifacts a JOIN aura_study_results r ON r.artifact_id=a.id
                JOIN sources s ON s.source_id=a.source_id JOIN courses c ON c.course_id=a.course_id
                WHERE a.student_id=%s AND a.course_id=%s AND s.owner_student_id=%s AND c.owner_student_id=%s ORDER BY r.completed_at DESC LIMIT 2000""",
                (
                    student["student_id"],
                    course_id,
                    student["student_id"],
                    student["student_id"],
                ),
            )
            for r in cur.fetchall():
                events.append(
                    {
                        "id": str(r["id"]),
                        "kind": "quiz",
                        "title": r["payload"].get("focus") or "Assessment",
                        "result": r["result"],
                        "duration_seconds": 0,
                        "created_at": instant(r["completed_at"]).isoformat(),
                    }
                )
            cur.execute(
                """SELECT count(*) AS n FROM aura_card_reviews r JOIN aura_study_artifacts a ON a.id=r.artifact_id
                JOIN sources s ON s.source_id=a.source_id WHERE r.student_id=%s AND r.course_id=%s AND s.owner_student_id=%s AND r.due_at<=NOW()""",
                (student["student_id"], course_id, student["student_id"]),
            )
            due = cur.fetchone()["n"]
        events.sort(key=lambda e: instant(e["created_at"]), reverse=True)
        return summarize(topics, events, due, range, timezone_name)

    app.include_router(router)
