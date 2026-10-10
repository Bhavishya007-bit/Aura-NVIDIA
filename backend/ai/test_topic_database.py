import os

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

from backend.ai.topic_database import TopicDatabase


load_dotenv("backend/.env")


# ==================================================
# DATABASE CONNECTION
# ==================================================

def get_connection():

    connection = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )

    register_vector(connection)

    return connection


# ==================================================
# CREATE TEST COURSE
# ==================================================

def create_test_course():

    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            SELECT course_id
            FROM courses
            WHERE course_name = %s
            LIMIT 1;
            """,
            ("Topic Database Test Course",)
        )

        row = cursor.fetchone()

        if row is not None:
            return row[0]

        cursor.execute(
            """
            INSERT INTO courses (
                course_name
            )
            VALUES (%s)
            RETURNING course_id;
            """,
            ("Topic Database Test Course",)
        )

        row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                "Failed to create test course."
            )

        connection.commit()

        return row[0]

    finally:

        cursor.close()
        connection.close()


# ==================================================
# CLEAN TEST DATA
# ==================================================

def clean_test_data(course_id):

    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            DELETE FROM topics
            WHERE course_id = %s;
            """,
            (course_id,)
        )

        connection.commit()

    finally:

        cursor.close()
        connection.close()


# ==================================================
# VERIFY DATABASE
# ==================================================

def verify_database(course_id):

    connection = get_connection()
    cursor = connection.cursor()

    try:

        # ------------------------------------------
        # Topics
        # ------------------------------------------

        cursor.execute(
            """
            SELECT
                topic_id,
                topic_name
            FROM topics
            WHERE course_id = %s
            ORDER BY topic_id;
            """,
            (course_id,)
        )

        topics = cursor.fetchall()

        print("\n")
        print("=" * 70)
        print("DATABASE TOPICS")
        print("=" * 70)

        print(
            "Number of topics:",
            len(topics)
        )

        assert len(topics) > 0

        for topic_id, topic_name in topics:

            print(
                f"Topic ID: {topic_id}"
            )

            print(
                f"Topic Name: {topic_name}"
            )

        # ------------------------------------------
        # Concepts
        # ------------------------------------------

        cursor.execute(
            """
            SELECT
                c.concept_id,
                c.concept_name,
                c.topic_id,
                t.topic_name
            FROM concepts c
            JOIN topics t
                ON c.topic_id = t.topic_id
            WHERE t.course_id = %s
            ORDER BY c.concept_id;
            """,
            (course_id,)
        )

        concepts = cursor.fetchall()

        print("\n")
        print("=" * 70)
        print("DATABASE CONCEPTS")
        print("=" * 70)

        print(
            "Number of concepts:",
            len(concepts)
        )

        assert len(concepts) > 0

        for (
            concept_id,
            concept_name,
            topic_id,
            topic_name,
        ) in concepts:

            print(
                f"Concept ID: {concept_id}"
            )

            print(
                f"Concept Name: {concept_name}"
            )

            print(
                f"Topic ID: {topic_id}"
            )

            print(
                f"Topic: {topic_name}"
            )

            print("-" * 50)

        return topics, concepts

    finally:

        cursor.close()
        connection.close()


# ==================================================
# MAIN TEST
# ==================================================

def main():

    print("\n")
    print("=" * 70)
    print("TOPIC DATABASE TEST")
    print("=" * 70)

    # ----------------------------------------------
    # Step 1
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 1: CREATE TEST COURSE")
    print("=" * 70)

    course_id = create_test_course()

    print(
        "Course ID:",
        course_id
    )

    # ----------------------------------------------
    # Step 2
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 2: CLEAN PREVIOUS TEST DATA")
    print("=" * 70)

    clean_test_data(course_id)

    print(
        "Previous test data removed."
    )

    # ----------------------------------------------
    # Step 3
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 3: CREATE TOPIC DATABASE")
    print("=" * 70)

    topic_database = TopicDatabase()

    print(
        "Topic database created."
    )

    # ----------------------------------------------
    # Step 4
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 4: STORE TOPICS AND CONCEPTS")
    print("=" * 70)

    topic_data = {
        "topics": [
            {
                "topic_name": "Oxidative Phosphorylation",
                "concepts": [
                    "Electron Transport Chain",
                    "Proton Gradient",
                    "ATP Synthase",
                ],
            }
        ]
    }

    stored_topics = topic_database.store_topics(
        course_id=course_id,
        topic_data=topic_data,
    )

    print(
        "Stored topics:",
        stored_topics
    )

    # ----------------------------------------------
    # Step 5
    # ----------------------------------------------

    topics, concepts = verify_database(
        course_id=course_id
    )

    # ----------------------------------------------
    # Step 6
    # ----------------------------------------------

    assert len(topics) == 1

    assert (
        topics[0][1]
        == "Oxidative Phosphorylation"
    )

    assert len(concepts) == 3

    concept_names = {
        concept[1]
        for concept in concepts
    }

    assert concept_names == {
        "Electron Transport Chain",
        "Proton Gradient",
        "ATP Synthase",
    }

    # ----------------------------------------------
    # Final
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("TOPIC DATABASE TEST: PASS")
    print("=" * 70)


if __name__ == "__main__":

    main()