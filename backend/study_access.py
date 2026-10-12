"""Authentication and ownership checks shared by saved study endpoints."""
from fastapi import Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from backend.auth_routes import get_current_student
from backend.auth_db import get_auth_connection


def _id(value) -> int:
    if isinstance(value, bool):
        raise HTTPException(status_code=422, detail="Invalid record ID.")
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid record ID.")
    if number < 1:
        raise HTTPException(status_code=422, detail="Invalid record ID.")
    return number


def _require_owner(kind: str, record_id: int, student_id: int) -> None:
    queries = {
        "attempt_id": "SELECT student_id FROM quiz_attempts WHERE attempt_id = %s",
        "session_id": "SELECT student_id FROM chat_sessions WHERE session_id = %s",
    }
    connection = get_auth_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(queries[kind], (record_id,))
            row = cursor.fetchone()
        # A missing or another student's record is not accessible.
        if row is None or row[0] != student_id:
            raise HTTPException(status_code=404, detail="Record not found.")
    finally:
        connection.close()


async def require_study_access(request: Request, student: dict = Depends(get_current_student)):
    """Runs before the route handler touches learner data or invokes AI."""
    student_id = _id(student["student_id"])
    values = [request.path_params, request.query_params]
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            body = await request.json() if await request.body() else {}
        except ValueError:
            raise HTTPException(status_code=422, detail="A JSON request body is required.")
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="Invalid request body.")
        values.append(body)
    checked = set()
    for fields in values:
        if fields.get("student_id") is not None and _id(fields["student_id"]) != student_id:
            raise HTTPException(status_code=403, detail="You can access only your own learning records.")
        for kind in ("attempt_id", "session_id"):
            if fields.get(kind) is not None:
                record_id = _id(fields[kind])
                if (kind, record_id) not in checked:
                    await run_in_threadpool(_require_owner, kind, record_id, student_id)
                    checked.add((kind, record_id))
    return student
