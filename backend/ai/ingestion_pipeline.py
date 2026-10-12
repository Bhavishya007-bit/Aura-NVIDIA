import os
from typing import Any

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

from backend.ingestion import ingest_file

from backend.ai.chunking import chunk_knowledge_unit
from backend.ai.chunk_topic_assignment import ChunkTopicAssignment
from backend.ai.embeddings import EmbeddingModel
from backend.ai.ingestion_adapter import (
    convert_ingestion_output,
)
from backend.ai.topic_assignment import TopicAssignment
from backend.ai.topic_database import TopicDatabase


load_dotenv("backend/.env")


class IngestionPipeline:
    """
    Complete ingestion pipeline.

    Flow:

        File
          ↓
        Ingestion
          ↓
        KnowledgeUnits
          ↓
        Topic + Concept extraction
          ↓
        Chunking
          ↓
        Chunk → Topic/Concept assignment
          ↓
        Embeddings
          ↓
        PostgreSQL + pgvector
    """

    def __init__(
        self,
        embedding_model: EmbeddingModel | None = None,
        topic_assignment: TopicAssignment | None = None,
        chunk_topic_assignment: ChunkTopicAssignment | None = None,
    ):

        self.embedding_model = (
            embedding_model
            if embedding_model is not None
            else EmbeddingModel()
        )

        self.topic_assignment = (
            topic_assignment
            if topic_assignment is not None
            else TopicAssignment()
        )

        self.chunk_topic_assignment = (
            chunk_topic_assignment
            if chunk_topic_assignment is not None
            else ChunkTopicAssignment()
        )

    # ==================================================
    # DATABASE CONNECTION
    # ==================================================

    def _get_connection(self):

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
    # CREATE / GET SOURCE
    # ==================================================

    def _get_or_create_source(
        self,
        connection,
        course_id: int,
        source_name: str,
        source_type: str,
        file_path: str | None = None,
    ) -> int:

        cursor = connection.cursor()

        try:

            cursor.execute(
                """
                SELECT source_id
                FROM sources
                WHERE course_id = %s
                  AND source_name = %s
                  AND source_type = %s
                ORDER BY source_id
                LIMIT 1;
                """,
                (
                    course_id,
                    source_name,
                    source_type,
                ),
            )

            row = cursor.fetchone()

            if row is not None:

                source_id = row[0]

                # Remove old chunks because the source
                # is being processed again.

                cursor.execute(
                    """
                    DELETE FROM chunks
                    WHERE source_id = %s;
                    """,
                    (source_id,),
                )

                cursor.execute(
                    """
                    UPDATE sources
                    SET file_path = %s,
                        status = %s
                    WHERE source_id = %s;
                    """,
                    (
                        file_path,
                        "PROCESSING",
                        source_id,
                    ),
                )

                connection.commit()

                return source_id

            # ------------------------------------------
            # Create new source
            # ------------------------------------------

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
                    source_name,
                    source_type,
                    file_path,
                    "PROCESSING",
                ),
            )

            row = cursor.fetchone()

            if row is None:

                raise RuntimeError(
                    "Failed to create source."
                )

            source_id = row[0]

            connection.commit()

            return source_id

        except Exception:

            connection.rollback()

            raise

        finally:

            cursor.close()

    # ==================================================
    # STORE CHUNKS
    # ==================================================

    def _store_chunks(
        self,
        connection,
        chunks,
        embeddings,
        assignment_map,
    ) -> list[int]:

        if len(chunks) != len(embeddings):

            raise ValueError(
                "Number of chunks and embeddings "
                "must be identical."
            )

        cursor = connection.cursor()

        inserted_ids = []

        try:

            for chunk, embedding in zip(
                chunks,
                embeddings,
            ):

                if len(embedding) != 1024:

                    raise ValueError(
                        "Embedding must contain "
                        "exactly 1024 values."
                    )

                assignment = assignment_map.get(
                    chunk.chunk_id
                )

                topic_id = None
                concept_id = None

                if assignment is not None:

                    topic_id = assignment.get(
                        "topic_id"
                    )

                    concept_id = assignment.get(
                        "concept_id"
                    )

                cursor.execute(
                    """
                    INSERT INTO chunks (
                        source_id,
                        topic_id,
                        concept_id,
                        content,
                        page_number,
                        slide_number,
                        timestamp_seconds,
                        timestamp_end,
                        metadata,
                        embedding
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    RETURNING chunk_id;
                    """,
                    (
                        chunk.source_id,
                        topic_id,
                        concept_id,
                        chunk.content,
                        chunk.page,
                        chunk.slide,
                        chunk.timestamp_start,
                        chunk.timestamp_end,
                        Json(
                            {
                                "chunk_id":
                                    chunk.chunk_id
                            }
                        ),
                        embedding,
                    ),
                )

                row = cursor.fetchone()

                if row is None:

                    raise RuntimeError(
                        "Failed to insert chunk."
                    )

                inserted_ids.append(
                    row[0]
                )

            connection.commit()

            return inserted_ids

        except Exception:

            connection.rollback()

            raise

        finally:

            cursor.close()

    # ==================================================
    # UPDATE SOURCE STATUS
    # ==================================================

    def _update_source_status(
        self,
        connection,
        source_id: int,
        status: str,
    ) -> None:

        cursor = connection.cursor()

        try:

            cursor.execute(
                """
                UPDATE sources
                SET status = %s
                WHERE source_id = %s;
                """,
                (
                    status,
                    source_id,
                ),
            )

            connection.commit()

        except Exception:

            connection.rollback()

            raise

        finally:

            cursor.close()

    # ==================================================
    # GET TOPIC / CONCEPT IDs
    # ==================================================

    def _get_topic_concept_ids(
        self,
        course_id: int,
        assignments: list[dict],
    ) -> dict:

        connection = self._get_connection()

        cursor = connection.cursor()

        assignment_map = {}

        try:

            for assignment in assignments:

                chunk_id = assignment.get(
                    "chunk_id"
                )

                topic_name = assignment.get(
                    "topic_name"
                )

                concept_name = assignment.get(
                    "concept_name"
                )

                if chunk_id is None:
                    continue

                if not topic_name:
                    continue

                # --------------------------------------
                # Find topic
                # --------------------------------------

                cursor.execute(
                    """
                    SELECT topic_id
                    FROM topics
                    WHERE course_id = %s
                      AND LOWER(topic_name) =
                          LOWER(%s)
                    LIMIT 1;
                    """,
                    (
                        course_id,
                        topic_name,
                    ),
                )

                topic_row = cursor.fetchone()

                if topic_row is None:
                    continue

                topic_id = topic_row[0]

                concept_id = None

                # --------------------------------------
                # Find concept
                # --------------------------------------

                if concept_name:

                    cursor.execute(
                        """
                        SELECT concept_id
                        FROM concepts
                        WHERE topic_id = %s
                          AND LOWER(concept_name) =
                              LOWER(%s)
                        LIMIT 1;
                        """,
                        (
                            topic_id,
                            concept_name,
                        ),
                    )

                    concept_row = cursor.fetchone()

                    if concept_row is not None:

                        concept_id = concept_row[0]

                assignment_map[
                    chunk_id
                ] = {
                    "topic_id": topic_id,
                    "concept_id": concept_id,
                }

            return assignment_map

        finally:

            cursor.close()
            connection.close()

    # ==================================================
    # PROCESS FILE
    # ==================================================

    def process_file(
        self,
        file,
        filename: str,
        course_id: int,
        file_path: str | None = None,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> dict[str, Any]:

        connection = None

        source_id = None

        try:

            # ==================================================
            # STEP 1: INGEST FILE
            # ==================================================

            ingestion_result = ingest_file(
                file=file,
                filename=filename,
            )

            ingestion_status = (
                ingestion_result.get(
                    "status"
                )
            )

            if ingestion_status not in {
                "success",
                "partial",
            }:

                return {
                    "status": ingestion_status,
                    "source_id": None,
                    "content_units": 0,
                    "chunks": 0,
                    "chunk_ids": [],
                    "topics": [],
                    "assignments": [],
                    "warnings":
                        ingestion_result.get(
                            "warnings",
                            [],
                        ),
                }

            # ==================================================
            # STEP 2: SOURCE
            # ==================================================

            source = ingestion_result.get(
                "source",
                {},
            )

            source_name = source.get(
                "filename",
                filename,
            )

            source_type = source.get(
                "file_type",
                "unknown",
            )

            connection = self._get_connection()

            source_id = self._get_or_create_source(
                connection=connection,
                course_id=course_id,
                source_name=source_name,
                source_type=source_type,
                file_path=file_path,
            )

            # ==================================================
            # STEP 3: CONVERT TO KNOWLEDGE UNITS
            # ==================================================

            knowledge_units = (
                convert_ingestion_output(
                    ingestion_result=ingestion_result,
                    source_id=source_id,
                )
            )

            if not knowledge_units:

                self._update_source_status(
                    connection,
                    source_id,
                    "EMPTY",
                )

                return {
                    "status": "empty",
                    "source_id": source_id,
                    "content_units": 0,
                    "chunks": 0,
                    "chunk_ids": [],
                    "topics": [],
                    "assignments": [],
                    "warnings":
                        ingestion_result.get(
                            "warnings",
                            [],
                        ),
                }

            # ==================================================
            # STEP 4: GENERATE TOPICS + CONCEPTS
            # ==================================================

            full_text = "\n\n".join(
                unit.content
                for unit in knowledge_units
                if unit.content
            )

            topic_data = (
                self.topic_assignment.assign(
                    text=full_text
                )
            )

            topics = topic_data.get(
                "topics",
                [],
            )

            # ==================================================
            # STEP 5: STORE TOPICS + CONCEPTS
            # ==================================================

            topic_database = TopicDatabase()

            try:

                stored_topics = (
                    topic_database.store_topics(
                        course_id=course_id,
                        topic_data=topic_data,
                    )
                )

            finally:

                topic_database.close()

            # ==================================================
            # STEP 6: CREATE CHUNKS
            # ==================================================

            all_chunks = []

            for unit in knowledge_units:

                chunks = chunk_knowledge_unit(
                    unit,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )

                all_chunks.extend(
                    chunks
                )

            if not all_chunks:

                self._update_source_status(
                    connection,
                    source_id,
                    "EMPTY",
                )

                return {
                    "status": "empty",
                    "source_id": source_id,
                    "content_units":
                        len(knowledge_units),
                    "chunks": 0,
                    "chunk_ids": [],
                    "topics": stored_topics,
                    "assignments": [],
                    "warnings":
                        ingestion_result.get(
                            "warnings",
                            [],
                        ),
                }

            # ==================================================
            # STEP 7: ASSIGN CHUNKS TO TOPICS / CONCEPTS
            # ==================================================

            chunk_input = []

            for chunk in all_chunks:

                chunk_input.append(
                    {
                        "chunk_id":
                            chunk.chunk_id,
                        "content":
                            chunk.content,
                    }
                )

            assignment_result = (
                self.chunk_topic_assignment.assign(
                    chunks=chunk_input,
                    topics=topics,
                )
            )

            assignments = (
                assignment_result.get(
                    "assignments",
                    [],
                )
            )

            # ==================================================
            # STEP 8: GET DATABASE IDS
            # ==================================================

            assignment_map = (
                self._get_topic_concept_ids(
                    course_id=course_id,
                    assignments=assignments,
                )
            )

            # ==================================================
            # STEP 9: CREATE EMBEDDINGS
            # ==================================================

            texts = [
                chunk.content
                for chunk in all_chunks
            ]

            embeddings = (
                self.embedding_model
                .embed_documents(texts)
            )

            # ==================================================
            # STEP 10: STORE CHUNKS
            # ==================================================

            chunk_ids = self._store_chunks(
                connection=connection,
                chunks=all_chunks,
                embeddings=embeddings,
                assignment_map=assignment_map,
            )

            # ==================================================
            # STEP 11: FINAL STATUS
            # ==================================================

            final_status = (
                "READY"
                if ingestion_status == "success"
                else "PARTIAL"
            )

            self._update_source_status(
                connection,
                source_id,
                final_status,
            )

            # ==================================================
            # RETURN RESULT
            # ==================================================

            return {
                "status": final_status,
                "source_id": source_id,
                "content_units":
                    len(knowledge_units),
                "chunks":
                    len(all_chunks),
                "chunk_ids":
                    chunk_ids,
                "topics":
                    stored_topics,
                "assignments":
                    assignments,
                "warnings":
                    ingestion_result.get(
                        "warnings",
                        [],
                    ),
            }

        except Exception as error:

            if connection is not None:

                try:

                    connection.rollback()

                    if source_id is not None:

                        self._update_source_status(
                            connection,
                            source_id,
                            "ERROR",
                        )

                except Exception:

                    pass

            raise RuntimeError(
                f"Ingestion pipeline failed: {error}"
            ) from error

        finally:

            if connection is not None:

                connection.close()