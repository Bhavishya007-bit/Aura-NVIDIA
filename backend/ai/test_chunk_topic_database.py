import os

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector


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
# VERIFY CHUNK TOPIC / CONCEPT ASSIGNMENTS
# ==================================================

def verify_assignments(
    source_id: int
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            SELECT
                c.chunk_id,
                c.content,
                c.topic_id,
                t.topic_name,
                c.concept_id,
                co.concept_name
            FROM chunks c
            LEFT JOIN topics t
                ON c.topic_id = t.topic_id
            LEFT JOIN concepts co
                ON c.concept_id = co.concept_id
            WHERE c.source_id = %s
            ORDER BY c.chunk_id;
            """,
            (source_id,)
        )

        rows = cursor.fetchall()

        print("\n")
        print("=" * 70)
        print("CHUNK TOPIC / CONCEPT DATABASE VERIFICATION")
        print("=" * 70)

        print(
            "Source ID:",
            source_id
        )

        print(
            "Number of chunks:",
            len(rows)
        )

        assert len(rows) > 0

        for row in rows:

            (
                chunk_id,
                content,
                topic_id,
                topic_name,
                concept_id,
                concept_name,
            ) = row

            print("\n")
            print("-" * 70)

            print(
                "Chunk ID:",
                chunk_id
            )

            print(
                "Content:",
                content
            )

            print(
                "Topic ID:",
                topic_id
            )

            print(
                "Topic Name:",
                topic_name
            )

            print(
                "Concept ID:",
                concept_id
            )

            print(
                "Concept Name:",
                concept_name
            )

            # ------------------------------------------
            # Validate topic
            # ------------------------------------------

            assert topic_id is not None

            assert topic_name is not None

            # ------------------------------------------
            # Validate concept
            # ------------------------------------------

            assert concept_id is not None

            assert concept_name is not None

            # ------------------------------------------
            # Verify concept belongs to topic
            # ------------------------------------------

            cursor.execute(
                """
                SELECT topic_id
                FROM concepts
                WHERE concept_id = %s;
                """,
                (concept_id,)
            )

            concept_row = cursor.fetchone()

            assert concept_row is not None

            assert (
                concept_row[0]
                == topic_id
            )

        return rows

    finally:

        cursor.close()
        connection.close()


# ==================================================
# FIND TEST SOURCE
# ==================================================

def find_test_source():

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            SELECT
                source_id,
                source_name,
                status
            FROM sources
            WHERE source_name = %s
            ORDER BY source_id DESC
            LIMIT 1;
            """,
            ("pipeline_test.pdf",)
        )

        row = cursor.fetchone()

        if row is None:

            raise RuntimeError(
                "Test source 'pipeline_test.pdf' "
                "was not found."
            )

        source_id = row[0]
        source_name = row[1]
        status = row[2]

        print("\n")
        print("=" * 70)
        print("TEST SOURCE")
        print("=" * 70)

        print(
            "Source ID:",
            source_id
        )

        print(
            "Source Name:",
            source_name
        )

        print(
            "Status:",
            status
        )

        assert status == "READY"

        return source_id

    finally:

        cursor.close()
        connection.close()


# ==================================================
# MAIN
# ==================================================

def main():

    print("\n")
    print("=" * 70)
    print("CHUNK TOPIC DATABASE TEST")
    print("=" * 70)

    # ----------------------------------------------
    # Step 1
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 1: FIND TEST SOURCE")
    print("=" * 70)

    source_id = find_test_source()

    # ----------------------------------------------
    # Step 2
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 2: VERIFY CHUNK ASSIGNMENTS")
    print("=" * 70)

    rows = verify_assignments(
        source_id=source_id
    )

    # ----------------------------------------------
    # Step 3
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 3: FINAL VALIDATION")
    print("=" * 70)

    for row in rows:

        topic_id = row[2]
        topic_name = row[3]
        concept_id = row[4]
        concept_name = row[5]

        assert topic_id is not None

        assert topic_name is not None

        assert concept_id is not None

        assert concept_name is not None

    print(
        "Every chunk has a valid topic."
    )

    print(
        "Every chunk has a valid concept."
    )

    print(
        "Every concept belongs to its assigned topic."
    )

    # ----------------------------------------------
    # Final
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("CHUNK TOPIC DATABASE TEST: PASS")
    print("=" * 70)


if __name__ == "__main__":

    main()