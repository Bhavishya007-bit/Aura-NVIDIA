import os
from typing import Any

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

from backend.ai.chunking import chunk_knowledge_unit
from backend.ai.embeddings import EmbeddingModel
from backend.ai.models import KnowledgeUnit
from backend.ai.pg_retrieval import PostgresRetriever


load_dotenv("backend/.env")


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


def setup_test_data():

    connection = get_connection()

    try:
        cursor = connection.cursor()

        # ---------------------------------------------------------
        # 1. Create or find a test course
        # ---------------------------------------------------------

        cursor.execute(
            """
            SELECT course_id
            FROM courses
            WHERE course_name = %s
            """,
            ("PGVector Test Course",)
        )

        course_row = cursor.fetchone()

        if course_row is not None:
            course_id = course_row[0]

        else:
            cursor.execute(
                """
                INSERT INTO courses (course_name)
                VALUES (%s)
                RETURNING course_id
                """,
                ("PGVector Test Course",)
            )

            course_row = cursor.fetchone()

            if course_row is None:
                raise RuntimeError(
                    "Failed to create course."
                )

            course_id = course_row[0]

        # ---------------------------------------------------------
        # 2. Create or find a test topic
        # ---------------------------------------------------------

        cursor.execute(
            """
            SELECT topic_id
            FROM topics
            WHERE course_id = %s
              AND topic_name = %s
            """,
            (course_id, "ATP Synthase")
        )

        topic_row = cursor.fetchone()

        if topic_row is not None:
            topic_id = topic_row[0]

        else:
            cursor.execute(
                """
                INSERT INTO topics (course_id, topic_name)
                VALUES (%s, %s)
                RETURNING topic_id
                """,
                (course_id, "ATP Synthase")
            )

            topic_row = cursor.fetchone()

            if topic_row is None:
                raise RuntimeError(
                    "Failed to create topic."
                )

            topic_id = topic_row[0]

        # ---------------------------------------------------------
        # 3. Create a test source
        # ---------------------------------------------------------

        cursor.execute(
            """
            INSERT INTO sources (
                course_id,
                source_name,
                source_type,
                page_number,
                status
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING source_id
            """,
            (
                course_id,
                "pgvector_test.pdf",
                "pdf",
                142,
                "UPLOADED",
            )
        )

        source_row = cursor.fetchone()

        if source_row is None:
            raise RuntimeError(
                "Failed to create source."
            )

        source_id = source_row[0]

        # ---------------------------------------------------------
        # 4. Create KnowledgeUnit
        # ---------------------------------------------------------

        unit = KnowledgeUnit(
            source_id=source_id,
            source_type="pdf",
            source_name="pgvector_test.pdf",
            content=(
                "ATP synthase is a molecular enzyme complex that "
                "produces ATP using the proton gradient across a "
                "membrane. Protons flow through ATP synthase, and "
                "the energy released by this movement drives the "
                "synthesis of ATP from ADP and inorganic phosphate."
            ),
            page=142,
            slide=None,
            timestamp_start=None,
            timestamp_end=None,
            topic="ATP Synthase",
        )

        # ---------------------------------------------------------
        # 5. Chunk the KnowledgeUnit
        # ---------------------------------------------------------

        chunks = chunk_knowledge_unit(
            unit,
            chunk_size=500,
            overlap=50,
        )

        print()
        print("=" * 60)
        print("CHUNKING")
        print("=" * 60)

        print(f"Created chunks: {len(chunks)}")

        if not chunks:
            raise RuntimeError(
                "Chunking produced no chunks."
            )

        # ---------------------------------------------------------
        # 6. Generate embeddings
        # ---------------------------------------------------------

        embedding_model = EmbeddingModel()

        texts = [
            chunk.content
            for chunk in chunks
        ]

        embeddings = embedding_model.embed_documents(
            texts
        )

        print()
        print("=" * 60)
        print("EMBEDDINGS")
        print("=" * 60)

        print(
            f"Number of embeddings: {len(embeddings)}"
        )

        print(
            f"Embedding dimension: {len(embeddings[0])}"
        )

        if len(embeddings[0]) != 1024:
            raise RuntimeError(
                "Expected 1024-dimensional embeddings, "
                f"but got {len(embeddings[0])}."
            )

        # ---------------------------------------------------------
        # 7. Insert chunks + embeddings into PostgreSQL
        # ---------------------------------------------------------

        for chunk, embedding in zip(
            chunks,
            embeddings,
        ):

            cursor.execute(
                """
                INSERT INTO chunks (
                    source_id,
                    topic_id,
                    content,
                    page_number,
                    slide_number,
                    timestamp_seconds,
                    timestamp_end,
                    metadata,
                    embedding
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
                    %s
                )
                """,
                (
                    source_id,
                    topic_id,
                    chunk.content,
                    chunk.page,
                    chunk.slide,
                    chunk.timestamp_start,
                    chunk.timestamp_end,
                    None,
                    embedding,
                )
            )

        connection.commit()

        print()
        print("=" * 60)
        print("POSTGRESQL INSERT")
        print("=" * 60)

        print(
            "Chunks inserted successfully."
        )

        return source_id

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def test_search():

    # ---------------------------------------------------------
    # 8. Create PostgreSQL retriever
    # ---------------------------------------------------------

    embedding_model = EmbeddingModel()

    retriever = PostgresRetriever(
        embedding_model=embedding_model
    )

    # ---------------------------------------------------------
    # 9. Search PostgreSQL using pgvector
    # ---------------------------------------------------------

    query = "How does ATP synthase produce ATP?"

    results = retriever.search(
        query=query,
        top_k=3,
        topic="ATP Synthase",
    )

    print()
    print("=" * 60)
    print("PGVECTOR SEARCH")
    print("=" * 60)

    print(f"Query: {query}")
    print(f"Results found: {len(results)}")

    # ---------------------------------------------------------
    # 10. Display results
    # ---------------------------------------------------------

    for index, result in enumerate(
        results,
        start=1,
    ):

        print()
        print(f"Result {index}")
        print("-" * 40)

        print(
            f"Score: {result.score:.4f}"
        )

        print(
            f"Source: {result.chunk.source_name}"
        )

        print(
            f"Page: {result.chunk.page}"
        )

        print(
            f"Topic: {result.chunk.topic}"
        )

        print(
            f"Content: {result.chunk.content}"
        )

    # ---------------------------------------------------------
    # 11. Verify retrieval
    # ---------------------------------------------------------

    if results:

        print()
        print("=" * 60)
        print("PGVECTOR RETRIEVAL TEST: PASS")
        print("=" * 60)

    else:

        print()
        print("=" * 60)
        print("PGVECTOR RETRIEVAL TEST: FAIL")
        print("=" * 60)

        raise RuntimeError(
            "No results were returned from pgvector search."
        )


def main():

    print()
    print("=" * 60)
    print("POSTGRESQL + PGVECTOR RETRIEVAL TEST")
    print("=" * 60)

    # Insert test data
    setup_test_data()

    # Search test data
    test_search()


if __name__ == "__main__":
    main()