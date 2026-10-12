import os
from typing import Any

from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
import psycopg2

from backend.ai.embeddings import EmbeddingModel
from backend.ai.models import Chunk, RetrievedChunk

load_dotenv("backend/.env")


class PostgresRetriever:
    def __init__(self, embedding_model: EmbeddingModel):
        self.embedding_model = embedding_model

    def _get_connection(self):
        connection = psycopg2.connect(
            dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"), host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
        )
        register_vector(connection)
        return connection

    def search(self, query: str, top_k: int = 3, topic: str | None = None,
               course_id: int | None = None, source_id: int | None = None) -> list[RetrievedChunk]:
        query_embedding = self.embedding_model.embed_query(query)
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                sql = r"""
                    WITH unique_passages AS (
                    SELECT chunks.chunk_id, chunks.source_id,
                           sources.source_name, sources.source_type, chunks.content,
                           chunks.page_number, chunks.slide_number,
                           chunks.timestamp_seconds, chunks.timestamp_end,
                           topics.topic_name, 1 - (chunks.embedding <=> %s) AS similarity,
                           ROW_NUMBER() OVER (
                               PARTITION BY md5(regexp_replace(lower(chunks.content), '\s+', ' ', 'g'))
                               ORDER BY CASE WHEN chunks.page_number IS NOT NULL
                                   OR chunks.slide_number IS NOT NULL
                                   OR chunks.timestamp_seconds IS NOT NULL THEN 0 ELSE 1 END,
                                   chunks.source_id DESC, chunks.chunk_id DESC
                           ) AS copy_rank
                    FROM chunks
                    JOIN sources ON chunks.source_id = sources.source_id
                    LEFT JOIN topics ON chunks.topic_id = topics.topic_id
                    WHERE chunks.embedding IS NOT NULL AND chunks.content IS NOT NULL
                      AND btrim(chunks.content) <> ''
                """
                params: list[Any] = [query_embedding]
                if course_id is not None:
                    sql += " AND sources.course_id = %s"
                    params.append(course_id)
                if source_id is not None:
                    sql += " AND chunks.source_id = %s"
                    params.append(source_id)
                if topic is not None:
                    sql += " AND topics.topic_name = %s"
                    params.append(topic)
                # Filter the scope before deduplication, and deduplicate before
                # LIMIT. Repeated uploads cannot consume the context window.
                sql += """
                    ) SELECT chunk_id, source_id, source_name, source_type, content,
                             page_number, slide_number, timestamp_seconds, timestamp_end,
                             topic_name, similarity
                      FROM unique_passages WHERE copy_rank = 1
                      ORDER BY similarity DESC, source_id DESC, chunk_id DESC LIMIT %s
                """
                params.append(top_k)
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            results = []
            for row in rows:
                (chunk_id, result_source_id, source_name, source_type, content,
                 page, slide, timestamp_start, timestamp_end, topic_name, similarity) = row
                chunk = Chunk(
                    chunk_id=str(chunk_id), source_id=result_source_id,
                    source_type=source_type, source_name=source_name, content=content,
                    page=page, slide=slide, timestamp_start=timestamp_start,
                    timestamp_end=timestamp_end, topic=topic_name,
                )
                results.append(RetrievedChunk(chunk=chunk, score=float(similarity)))
            return results
        finally:
            connection.close()

    def is_relevant(self, query: str, topic: str | None = None,
                    course_id: int | None = None, source_id: int | None = None,
                    threshold: float = 0.50) -> bool:
        results = self.search(query=query, top_k=1, topic=topic,
                              course_id=course_id, source_id=source_id)
        return bool(results) and results[0].score >= threshold
