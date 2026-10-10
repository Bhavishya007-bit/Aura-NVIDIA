import io
import os

import pymupdf
import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

from backend.ai.embeddings import EmbeddingModel
from backend.ai.ingestion_pipeline import IngestionPipeline


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
# CREATE TEST PDF
# ==================================================

def create_test_pdf() -> bytes:

    document = pymupdf.open()

    page_1 = document.new_page()

    page_1.insert_text(
        (72, 72),
        (
            "ATP synthase is an enzyme that produces ATP "
            "using the proton gradient across a membrane. "
            "Protons move through ATP synthase and the "
            "energy released drives ATP production."
        )
    )

    page_2 = document.new_page()

    page_2.insert_text(
        (72, 72),
        (
            "The electron transport chain consists of "
            "protein complexes in the inner mitochondrial "
            "membrane. These complexes transfer electrons "
            "and pump protons across the membrane."
        )
    )

    buffer = io.BytesIO()

    document.save(buffer)

    document.close()

    return buffer.getvalue()


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
            ("Ingestion Pipeline Test Course",)
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
            ("Ingestion Pipeline Test Course",)
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
# VERIFY DATABASE
# ==================================================

def verify_database(
    course_id: int,
    source_id: int
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        # ------------------------------------------
        # Check source
        # ------------------------------------------

        cursor.execute(
            """
            SELECT
                source_id,
                source_name,
                source_type,
                status
            FROM sources
            WHERE source_id = %s;
            """,
            (source_id,)
        )

        source = cursor.fetchone()

        if source is None:

            raise RuntimeError(
                "Source was not found in database."
            )

        print("\n")
        print("=" * 70)
        print("DATABASE SOURCE")
        print("=" * 70)

        print("Source ID:", source[0])
        print("Source Name:", source[1])
        print("Source Type:", source[2])
        print("Status:", source[3])

        assert source[3] == "READY"

        # ------------------------------------------
        # Check chunks
        # ------------------------------------------

        cursor.execute(
            """
            SELECT
                chunk_id,
                content,
                page_number,
                embedding
            FROM chunks
            WHERE source_id = %s
            ORDER BY chunk_id;
            """,
            (source_id,)
        )

        chunks = cursor.fetchall()

        print("\n")
        print("=" * 70)
        print("DATABASE CHUNKS")
        print("=" * 70)

        print(
            "Number of chunks:",
            len(chunks)
        )

        assert len(chunks) > 0

        for chunk in chunks:

            chunk_id = chunk[0]
            content = chunk[1]
            page = chunk[2]
            embedding = chunk[3]

            print("-" * 50)

            print(
                "Chunk ID:",
                chunk_id
            )

            print(
                "Page:",
                page
            )

            print(
                "Content:",
                content
            )

            if embedding is None:

                raise RuntimeError(
                    f"Chunk {chunk_id} "
                    "has no embedding."
                )

            # pgvector returns a Vector object.
            # Convert it to a Python list before
            # checking its length.

            embedding_dimension = len(
                embedding.to_list()
            )

            print(
                "Embedding dimension:",
                embedding_dimension
            )

            assert embedding_dimension == 1024

        # ------------------------------------------
        # Check course relationship
        # ------------------------------------------

        cursor.execute(
            """
            SELECT course_id
            FROM sources
            WHERE source_id = %s;
            """,
            (source_id,)
        )

        source_course = cursor.fetchone()

        assert source_course is not None

        assert source_course[0] == course_id

    finally:

        cursor.close()
        connection.close()


# ==================================================
# MAIN TEST
# ==================================================

def main():

    print("\n")
    print("=" * 70)
    print("FULL INGESTION PIPELINE TEST")
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
    print("STEP 2: CREATE TEST PDF")
    print("=" * 70)

    pdf_data = create_test_pdf()

    print(
        "PDF bytes:",
        len(pdf_data)
    )

    # ----------------------------------------------
    # Step 3
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 3: CREATE EMBEDDING MODEL")
    print("=" * 70)

    embedding_model = EmbeddingModel()

    print(
        "Embedding model created."
    )

    # ----------------------------------------------
    # Step 4
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 4: CREATE INGESTION PIPELINE")
    print("=" * 70)

    pipeline = IngestionPipeline(
        embedding_model=embedding_model
    )

    print(
        "Ingestion pipeline created."
    )

    # ----------------------------------------------
    # Step 5
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 5: PROCESS PDF")
    print("=" * 70)

    result = pipeline.process_file(
        file=pdf_data,
        filename="pipeline_test.pdf",
        course_id=course_id,
        file_path="test/pipeline_test.pdf",
        chunk_size=300,
        overlap=50,
    )

    print(
        "Pipeline status:",
        result["status"]
    )

    print(
        "Source ID:",
        result["source_id"]
    )

    print(
        "Content units:",
        result["content_units"]
    )

    print(
        "Chunks:",
        result["chunks"]
    )

    print(
        "Chunk IDs:",
        result["chunk_ids"]
    )

    print(
        "Warnings:",
        result["warnings"]
    )

    assert result["status"] == "READY"

    assert result["source_id"] is not None

    assert result["content_units"] == 2

    assert result["chunks"] > 0

    assert len(
        result["chunk_ids"]
    ) == result["chunks"]

    # ----------------------------------------------
    # Step 6
    # ----------------------------------------------

    verify_database(
        course_id=course_id,
        source_id=result["source_id"]
    )

    # ----------------------------------------------
    # Final
    # ----------------------------------------------

    print("\n")
    print("=" * 70)
    print("FULL INGESTION PIPELINE TEST: PASS")
    print("=" * 70)


if __name__ == "__main__":

    main()