"""Seed an isolated judge account with original synthetic study notes only."""

import os
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from backend.auth_db import get_auth_connection
from backend.auth_security import hash_password
from backend.production.config import flag

SECTIONS = [
    (
        "Dictionaries and hash tables",
        "A dictionary stores key-value pairs. A hash table maps each key to an array slot using a hash function. Average lookup can be constant time with suitable hashing and controlled load, while worst-case lookup can be linear.",
    ),
    (
        "Collisions",
        "Distinct keys can map to the same slot. Separate chaining stores colliding entries in a collection at that slot. Open addressing probes other slots in the table. A load factor describes how full the table is.",
    ),
    (
        "Search",
        "Linear search visits entries in sequence and works on unsorted data. Binary search requires sorted data and repeatedly halves the remaining interval. Linear search is O(n) in the worst case; binary search is O(log n).",
    ),
    (
        "Worked search example",
        "For the sorted list [2, 5, 8, 12, 16, 23, 38, 42, 57], binary search for 23 first checks 16, then 38, then 23 when the lower middle index is used. That takes three visited elements. Linear search visits six elements.",
    ),
    (
        "Numerical practice",
        "Speed = distance / time. For a clearly stated hypothetical trip of 120 metres in 10 seconds, the speed is 12 metres per second. Convert units consistently before comparing measurements.",
    ),
    (
        "Review checklist",
        "Explain why collisions occur. Compare chaining with open addressing. State when binary search is applicable. Trace the search example. Calculate speed from the given distance and time. These synthetic notes and examples were authored for the Aura demo and contain no student documents.",
    ),
]


def write_demo_pdf(path):
    import pymupdf

    doc = pymupdf.open()
    try:
        for title, text in SECTIONS:
            page = doc.new_page()
            page.insert_text((50, 65), title, fontsize=19)
            page.insert_textbox(pymupdf.Rect(50, 105, 545, 750), text, fontsize=13)
        doc.save(path)
    finally:
        doc.close()


def seed_demo():
    if not flag("AURA_DEMO_ENABLED"):
        return
    email = os.getenv("AURA_DEMO_EMAIL", "judge@aura.example.org").strip().lower()
    password = os.environ["AURA_DEMO_PASSWORD"]
    con = get_auth_connection()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(817266,3)")
            cur.execute(
                "SELECT student_id FROM students WHERE LOWER(email)=%s", (email,)
            )
            row = cur.fetchone()
            if row:
                student = row[0]
                cur.execute(
                    "SELECT student_id FROM aura_demo_accounts WHERE student_id=%s",
                    (student,),
                )
                if not cur.fetchone():
                    raise RuntimeError(
                        "The demo email belongs to an existing non-demo account. Choose another email."
                    )
                cur.execute(
                    "UPDATE students SET password_hash=%s WHERE student_id=%s",
                    (hash_password(password), student),
                )
            else:
                cur.execute(
                    "INSERT INTO students(name,email,password_hash) VALUES(%s,%s,%s) RETURNING student_id",
                    ("Aura Demo Learner", email, hash_password(password)),
                )
                student = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO aura_demo_accounts(student_id) VALUES(%s)", (student,)
                )
            cur.execute(
                "INSERT INTO courses(course_name,owner_student_id) VALUES('Demo study workspace',%s) ON CONFLICT(owner_student_id) DO UPDATE SET course_name=courses.course_name RETURNING course_id",
                (student,),
            )
            course = cur.fetchone()[0]
            job = str(uuid5(NAMESPACE_URL, "aura-synthetic-demo-v1:" + email))
            cur.execute("SELECT id FROM aura_preparation_jobs WHERE id=%s", (job,))
            if not cur.fetchone():
                directory = (
                    Path(__file__).resolve().parents[1] / "uploads" / "preparation"
                )
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / (job + ".pdf")
                write_demo_pdf(path)
                cur.execute(
                    "INSERT INTO aura_preparation_jobs(id,student_id,course_id,filename,staged_path) VALUES(%s,%s,%s,%s,%s)",
                    (job, student, course, "Aura Demo Study Notes.pdf", str(path)),
                )
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
