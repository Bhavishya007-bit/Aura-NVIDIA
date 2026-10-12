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
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
        )
        register_vector(connection)
        return connection

    def search(
        self,
        query: str,
        top_k: int = 3,
        topic: str | None = None,
        course_id: int | None = None,
        source_id: int | None = None,
        owner_student_id: int | None = None,
    ) -> list[RetrievedChunk]:
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
                if owner_student_id is not None:
                    sql += " AND sources.owner_student_id = %s"
                    params.append(owner_student_id)
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
                (
                    chunk_id,
                    result_source_id,
                    source_name,
                    source_type,
                    content,
                    page,
                    slide,
                    timestamp_start,
                    timestamp_end,
                    topic_name,
                    similarity,
                ) = row
                chunk = Chunk(
                    chunk_id=str(chunk_id),
                    source_id=result_source_id,
                    source_type=source_type,
                    source_name=source_name,
                    content=content,
                    page=page,
                    slide=slide,
                    timestamp_start=timestamp_start,
                    timestamp_end=timestamp_end,
                    topic=topic_name,
                )
                results.append(RetrievedChunk(chunk=chunk, score=float(similarity)))
            return results
        finally:
            connection.close()

    def overview(
        self,
        course_id: int,
        source_id: int,
        owner_student_id: int,
        limit: int = 12,
    ) -> list[RetrievedChunk]:
        """Read diverse source locations; vague file questions need no embedding."""
        if not course_id or not source_id or not owner_student_id:
            raise ValueError(
                "A material overview requires its course, source and owner."
            )
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT chunks.chunk_id, chunks.source_id,
                           sources.source_name, sources.source_type, chunks.content,
                           chunks.page_number, chunks.slide_number,
                           chunks.timestamp_seconds, chunks.timestamp_end,
                           topics.topic_name
                    FROM chunks
                    JOIN sources ON sources.source_id = chunks.source_id
                    JOIN courses ON courses.course_id = sources.course_id
                    LEFT JOIN topics ON topics.topic_id = chunks.topic_id
                    WHERE sources.course_id = %s AND sources.source_id = %s
                      AND sources.owner_student_id = %s
                      AND courses.owner_student_id = %s
                      AND chunks.content IS NOT NULL AND btrim(chunks.content) <> ''
                    ORDER BY chunks.page_number NULLS LAST,
                             chunks.slide_number NULLS LAST,
                             chunks.timestamp_seconds NULLS LAST, chunks.chunk_id
                    """,
                    (course_id, source_id, owner_student_id, owner_student_id),
                )
                rows = cursor.fetchall()
            # One substantial passage per location prevents a dense page from
            # crowding out the rest of a presentation. Keep exact origin metadata.
            locations = {}
            seen = set()
            for row in rows:
                normalized = " ".join(row[4].casefold().split())
                if normalized in seen:
                    continue
                seen.add(normalized)
                location = tuple(row[5:8])
                if location == (None, None, None):
                    location = ("chunk", row[0])
                if location not in locations or len(row[4].split()) > len(
                    locations[location][4].split()
                ):
                    locations[location] = row
            candidates = list(locations.values())
            count = max(2, min(int(limit), 16))
            if len(candidates) > count:
                # Preserve the opening title/introduction, then sample through
                # the middle and end rather than retrieving only similar slides.
                indices = (
                    {0, len(candidates) - 1}
                    if count == 2
                    else {0, 1, len(candidates) - 1}
                )
                if count > 3:
                    indices.update(
                        round(2 + i * (len(candidates) - 3) / (count - 3))
                        for i in range(count - 2)
                    )
                candidates = [candidates[i] for i in sorted(indices)[:count]]
            return [
                RetrievedChunk(
                    chunk=Chunk(
                        chunk_id=str(row[0]),
                        source_id=row[1],
                        source_name=row[2],
                        source_type=row[3],
                        content=row[4],
                        page=row[5],
                        slide=row[6],
                        timestamp_start=row[7],
                        timestamp_end=row[8],
                        topic=row[9],
                    ),
                    score=0.0,
                )
                for row in candidates
            ]
        finally:
            connection.close()

    def is_relevant(
        self,
        query: str,
        topic: str | None = None,
        course_id: int | None = None,
        source_id: int | None = None,
        threshold: float = 0.50,
    ) -> bool:
        results = self.search(
            query=query, top_k=1, topic=topic, course_id=course_id, source_id=source_id
        )
        return bool(results) and results[0].score >= threshold
