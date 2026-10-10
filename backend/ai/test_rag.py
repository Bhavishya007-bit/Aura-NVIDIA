import os

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

from backend.ai.models import KnowledgeUnit
from backend.ai.chunking import chunk_knowledge_unit
from backend.ai.embeddings import EmbeddingModel
from backend.ai.pg_retrieval import PostgresRetriever
from backend.ai.llm import LLM
from backend.ai.rag import RAG


# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

load_dotenv("backend/.env")


# --------------------------------------------------
# PostgreSQL connection
# --------------------------------------------------

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


# --------------------------------------------------
# 1. Create sample course material
# --------------------------------------------------

text = """
ATP synthase is an important enzyme involved in oxidative phosphorylation.
It uses the proton gradient across the inner mitochondrial membrane.
The movement of protons through ATP synthase provides energy for ATP production.

The electron transport chain consists of several protein complexes located
in the inner mitochondrial membrane. These complexes transfer electrons
and use the released energy to pump protons across the membrane.

DNA replication is the process by which a cell copies its DNA before cell
division. DNA polymerase adds nucleotides to the growing DNA strand.
"""


unit = KnowledgeUnit(
    source_id=1,
    source_type="pdf",
    source_name="Biochemistry.pdf",
    content=text,
    page=142,
    topic="Biochemistry"
)


# --------------------------------------------------
# 2. Chunk the material
# --------------------------------------------------

chunks = chunk_knowledge_unit(
    unit,
    chunk_size=250,
    overlap=50
)


print("\n")
print("=" * 70)
print("CHUNKING")
print("=" * 70)

print(f"Created chunks: {len(chunks)}")

for index, chunk in enumerate(chunks, start=1):

    print(f"\nChunk {index}")
    print("-" * 70)
    print(chunk.content)


if not chunks:
    raise RuntimeError("Chunking produced no chunks.")


# --------------------------------------------------
# 3. Create embedding model
# --------------------------------------------------

print("\n")
print("=" * 70)
print("EMBEDDING MODEL")
print("=" * 70)

print("Loading embedding model...")

embedding_model = EmbeddingModel()

embeddings = embedding_model.embed_documents(
    [chunk.content for chunk in chunks]
)

print(f"Number of embeddings: {len(embeddings)}")
print(f"Embedding dimension: {len(embeddings[0])}")


if len(embeddings[0]) != 1024:

    raise RuntimeError(
        f"Expected 1024-dimensional embeddings, "
        f"but got {len(embeddings[0])}."
    )


# --------------------------------------------------
# 4. Insert test chunks into PostgreSQL
# --------------------------------------------------

print("\n")
print("=" * 70)
print("POSTGRESQL INSERT")
print("=" * 70)

connection = get_connection()

try:

    cursor = connection.cursor()

    # --------------------------------------------------
    # Create/find test course
    # --------------------------------------------------

    cursor.execute(
        """
        SELECT course_id
        FROM courses
        WHERE course_name = %s
        """,
        ("RAG Test Course",)
    )

    course_row = cursor.fetchone()

    if course_row:

        course_id = course_row[0]

    else:

        cursor.execute(
            """
            INSERT INTO courses (course_name)
            VALUES (%s)
            RETURNING course_id
            """,
            ("RAG Test Course",)
        )

        course_row = cursor.fetchone()

        if course_row is None:

            raise RuntimeError(
                "Failed to create test course."
            )

        course_id = course_row[0]


    # --------------------------------------------------
    # Create/find test topic
    # --------------------------------------------------

    cursor.execute(
        """
        SELECT topic_id
        FROM topics
        WHERE course_id = %s
        AND topic_name = %s
        """,
        (
            course_id,
            "Biochemistry"
        )
    )

    topic_row = cursor.fetchone()

    if topic_row:

        topic_id = topic_row[0]

    else:

        cursor.execute(
            """
            INSERT INTO topics (
                course_id,
                topic_name
            )
            VALUES (%s, %s)
            RETURNING topic_id
            """,
            (
                course_id,
                "Biochemistry"
            )
        )

        topic_row = cursor.fetchone()

        if topic_row is None:

            raise RuntimeError(
                "Failed to create test topic."
            )

        topic_id = topic_row[0]


    # --------------------------------------------------
    # Create test source
    # --------------------------------------------------

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
            "Biochemistry.pdf",
            "pdf",
            142,
            "READY"
        )
    )

    source_row = cursor.fetchone()

    if source_row is None:

        raise RuntimeError(
            "Failed to create test source."
        )

    source_id = source_row[0]


    # --------------------------------------------------
    # Insert chunks + embeddings
    # --------------------------------------------------

    for chunk, embedding in zip(chunks, embeddings):

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
                embedding
            )
        )


    connection.commit()

    print("Chunks inserted successfully.")
    print(f"Source ID: {source_id}")
    print(f"Topic ID: {topic_id}")

finally:

    connection.close()


# --------------------------------------------------
# 5. Create PostgreSQL retriever
# --------------------------------------------------

print("\n")
print("=" * 70)
print("POSTGRESQL RETRIEVER")
print("=" * 70)

retriever = PostgresRetriever(
    embedding_model=embedding_model
)

print("PostgresRetriever created successfully.")


# --------------------------------------------------
# 6. Create LLM
# --------------------------------------------------

print("\n")
print("=" * 70)
print("LLM")
print("=" * 70)

print("Loading LLM...")

llm = LLM()

print("LLM created successfully.")


# --------------------------------------------------
# 7. Create RAG system
# --------------------------------------------------

rag = RAG(
    retriever=retriever,
    llm=llm
)

print("RAG system created successfully.")


# --------------------------------------------------
# 8. Test question inside the material
# --------------------------------------------------

question_1 = "How does ATP synthase produce ATP?"

result_1 = rag.answer(
    question_1,
    top_k=3
)


print("\n")
print("=" * 70)
print("QUESTION 1")
print("=" * 70)

print(question_1)

print("\nANSWER")
print("-" * 70)

print(result_1["answer"])

print("\nSOURCES")
print("-" * 70)

for source in result_1["sources"]:

    print(f"Source ID: {source['source_id']}")
    print(f"File: {source['source_name']}")
    print(f"Page: {source['page']}")
    print(f"Similarity: {source['score']:.4f}")
    print()


# --------------------------------------------------
# 9. Test question outside the material
# --------------------------------------------------

question_2 = "What is the capital of France?"

result_2 = rag.answer(
    question_2,
    top_k=3
)


print("\n")
print("=" * 70)
print("QUESTION 2")
print("=" * 70)

print(question_2)

print("\nANSWER")
print("-" * 70)

print(result_2["answer"])

print("\nSOURCES")
print("-" * 70)

if result_2["sources"]:

    for source in result_2["sources"]:

        print(f"Source ID: {source['source_id']}")
        print(f"File: {source['source_name']}")
        print(f"Page: {source['page']}")
        print(f"Similarity: {source['score']:.4f}")
        print()

else:

    print("No sources returned.")


# --------------------------------------------------
# 10. Final result
# --------------------------------------------------

print("\n")
print("=" * 70)
print("RAG TEST COMPLETE")
print("=" * 70)