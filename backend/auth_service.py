
from psycopg2 import IntegrityError

from backend.auth_db import get_auth_connection
from backend.auth_security import hash_password, verify_password


def register_student(name: str, email: str, password: str) -> dict:
    """Register a new student account."""
    connection = get_auth_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO students (name, email, password_hash)
                VALUES (%s, %s, %s)
                RETURNING student_id, name, email
                """,
                (name.strip(), email.strip().lower(), hash_password(password)),
            )
            row = cursor.fetchone()

        connection.commit()

        return {
            "student_id": row[0],
            "name": row[1],
            "email": row[2],
        }

    except IntegrityError:
        connection.rollback()
        raise ValueError("An account with this email already exists.")

    finally:
        connection.close()


def student_email_exists(email: str) -> bool:
    connection = get_auth_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM students WHERE LOWER(email) = LOWER(%s)", (email.strip(),))
            return cursor.fetchone() is not None
    finally:
        connection.close()


def authenticate_student(email: str, password: str) -> dict | None:
    """Verify login credentials without revealing whether an email exists."""
    connection = get_auth_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT student_id, name, email, password_hash
                FROM students
                WHERE LOWER(email) = LOWER(%s)
                """,
                (email.strip(),),
            )
            row = cursor.fetchone()

        if not row or not row[3]:
            return None

        if not verify_password(password, row[3]):
            return None

        return {
            "student_id": row[0],
            "name": row[1],
            "email": row[2],
        }

    finally:
        connection.close()
