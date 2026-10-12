from backend.main import get_connection
from psycopg2.extras import Json


def seed_data():
    connection = get_connection()
    cursor = connection.cursor()

    try:
        # =========================================================
        # 1. Student
        # =========================================================

        cursor.execute(
            """
            INSERT INTO students (name, email)
            VALUES (%s, %s)
            ON CONFLICT (email)
            DO UPDATE SET name = EXCLUDED.name
            RETURNING student_id;
            """,
            (
                "Demo Student",
                "demo@student.com",
            ),
        )

        student_row = cursor.fetchone()

        if student_row is None:
            raise RuntimeError(
                "Failed to create or retrieve student."
            )

        student_id = student_row[0]

        # =========================================================
        # 2. Course
        # =========================================================

        cursor.execute(
            """
            INSERT INTO courses (course_name)
            VALUES (%s)
            RETURNING course_id;
            """,
            (
                "Database Management Systems",
            ),
        )

        course_row = cursor.fetchone()

        if course_row is None:
            raise RuntimeError(
                "Failed to create course."
            )

        course_id = course_row[0]

        # =========================================================
        # 3. Topic
        # =========================================================

        cursor.execute(
            """
            INSERT INTO topics (
                course_id,
                topic_name
            )
            VALUES (%s, %s)
            RETURNING topic_id;
            """,
            (
                course_id,
                "SQL",
            ),
        )

        topic_row = cursor.fetchone()

        if topic_row is None:
            raise RuntimeError(
                "Failed to create topic."
            )

        topic_id = topic_row[0]

        # =========================================================
        # 4. Concept
        # =========================================================

        cursor.execute(
            """
            INSERT INTO concepts (
                topic_id,
                concept_name
            )
            VALUES (%s, %s)
            RETURNING concept_id;
            """,
            (
                topic_id,
                "SQL Joins",
            ),
        )

        concept_row = cursor.fetchone()

        if concept_row is None:
            raise RuntimeError(
                "Failed to create concept."
            )

        concept_id = concept_row[0]

        # =========================================================
        # 5. Source
        # =========================================================

        cursor.execute(
            """
            INSERT INTO sources (
                course_id,
                source_name,
                source_type,
                file_path,
                status
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING source_id;
            """,
            (
                course_id,
                "DBMS Demo Lecture",
                "textbook",
                "demo/DBMS_Demo.pdf",
                "READY",
            ),
        )

        source_row = cursor.fetchone()

        if source_row is None:
            raise RuntimeError(
                "Failed to create source."
            )

        source_id = source_row[0]

        # =========================================================
        # 6. Question
        # =========================================================

        cursor.execute(
            """
            INSERT INTO questions (
                topic_id,
                source_id,
                concept_id,
                question_text,
                difficulty,
                correct_answer,
                question_type,
                options,
                explanation,
                verified
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            RETURNING question_id;
            """,
            (
                topic_id,
                source_id,
                concept_id,
                "Which SQL command is used to retrieve data?",
                1,
                "SELECT",
                "MCQ",
                Json(
                    {
                        "A": "SELECT",
                        "B": "INSERT",
                        "C": "UPDATE",
                        "D": "DELETE",
                    }
                ),
                "SELECT is used to retrieve data from a table.",
                True,
            ),
        )

        question_row = cursor.fetchone()

        if question_row is None:
            raise RuntimeError(
                "Failed to create question."
            )

        question_id = question_row[0]

        # =========================================================
        # 7. Concept Mastery
        # =========================================================

        cursor.execute(
            """
            INSERT INTO concept_mastery (
                student_id,
                concept_id,
                mastery_score
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (
                student_id,
                concept_id
            )
            DO UPDATE SET
                mastery_score = EXCLUDED.mastery_score,
                last_updated = CURRENT_TIMESTAMP;
            """,
            (
                student_id,
                concept_id,
                0.75,
            ),
        )

        # =========================================================
        # 8. Mastery History
        # =========================================================

        cursor.execute(
            """
            INSERT INTO mastery_history (
                student_id,
                concept_id,
                mastery_score
            )
            VALUES (%s, %s, %s);
            """,
            (
                student_id,
                concept_id,
                0.75,
            ),
        )

        # =========================================================
        # Commit
        # =========================================================

        connection.commit()

        print()
        print("=" * 50)
        print("Demo data seeded successfully!")
        print("=" * 50)

        print("Student ID:", student_id)
        print("Course ID:", course_id)
        print("Topic ID:", topic_id)
        print("Concept ID:", concept_id)
        print("Source ID:", source_id)
        print("Question ID:", question_id)

    except Exception as error:

        connection.rollback()

        print()
        print("=" * 50)
        print("ERROR WHILE SEEDING DATA")
        print("=" * 50)

        print(error)

    finally:

        cursor.close()
        connection.close()


if __name__ == "__main__":
    seed_data()