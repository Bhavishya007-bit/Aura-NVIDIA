import os
from typing import Any

from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
import psycopg2

from backend.ai.embeddings import EmbeddingModel, get_embedding_model, LEGACY_MODEL
from backend.ai.models import Chunk, RetrievedChunk
from backend.ai.grounded_expansion import topic_terms

load_dotenv("backend/.env")


class PostgresRetriever:
    def __init__(self, embedding_model: EmbeddingModel | None = None):
        self._embedding_model = embedding_model

    @property
    def embedding_model(self):
        return self._embedding_model or get_embedding_model(LEGACY_MODEL)

    def _model_cohorts(self, cursor, course_id, source_id, owner_student_id, topic):
        sql = """SELECT DISTINCT COALESCE(sources.metadata->>'embedding_model', %s)
                 FROM sources JOIN chunks ON chunks.source_id=sources.source_id
                 LEFT JOIN topics ON topics.topic_id=chunks.topic_id
                 WHERE chunks.embedding IS NOT NULL"""
        params = [LEGACY_MODEL]
        for column, value in [
            ("sources.course_id", course_id),
            ("sources.source_id", source_id),
            ("sources.owner_student_id", owner_student_id),
            ("topics.topic_name", topic),
        ]:
            if value is not None:
                sql += f" AND {column} = %s"
                params.append(value)
        cursor.execute(sql, params)
        return [row[0] for row in cursor.fetchall()]

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
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                cohorts = self._model_cohorts(
                    cursor, course_id, source_id, owner_student_id, topic
                )
                ranked_rows: list[list[tuple[Any, ...]]] = []
                for model_name in sorted(cohorts):
                    model = self._embedding_model or get_embedding_model(model_name)
                    if getattr(model, "model_name", model_name) != model_name:
                        raise ValueError(
                            "Query encoder does not match this material's stored vectors."
                        )
                    query_embedding = model.embed_query(query)
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
                    sql += (
                        " AND COALESCE(sources.metadata->>'embedding_model', %s) = %s"
                    )
                    params.extend([LEGACY_MODEL, model_name])
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
                    ranked_rows.append(cursor.fetchall())
            # Searches over one selected material use its actual cosine score.
            # A course with mixed encoders uses rank fusion, not incompatible
            # cross-model cosine comparisons.
            if len(ranked_rows) <= 1:
                rows = ranked_rows[0] if ranked_rows else []
            else:
                fused: list[tuple[Any, ...]] = [
                    (tuple(row[:-1]) + (1.0 / (60 + rank),))
                    for group in ranked_rows
                    for rank, row in enumerate(group, 1)
                ]
                rows = []
                seen = set()
                for candidate in sorted(
                    fused, key=lambda row: (-row[-1], -row[1], str(row[0]))
                ):
                    key = " ".join(candidate[4].casefold().split())
                    if key not in seen:
                        seen.add(key)
                        rows.append(candidate)
                    if len(rows) >= top_k:
                        break
            results = []
            for row in rows:
                chunk = Chunk(
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
                )
                results.append(RetrievedChunk(chunk=chunk, score=float(row[10])))
            return results
        finally:
            connection.close()

    def concept_context(self, query: str, course_id: int, source_id: int,
                        owner_student_id: int, limit: int = 6) -> list[RetrievedChunk]:
        """Literal concept matches plus nearby locations, within the owned file."""
        terms = topic_terms(query)
        if not terms or not course_id or not source_id or not owner_student_id:
            return []
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                fields = """chunks.chunk_id,chunks.source_id,sources.source_name,sources.source_type,
                            chunks.content,chunks.page_number,chunks.slide_number,chunks.timestamp_seconds,
                            chunks.timestamp_end,topics.topic_name"""
                base = """ FROM chunks JOIN sources ON chunks.source_id=sources.source_id
                          JOIN courses ON courses.course_id=sources.course_id
                          LEFT JOIN topics ON topics.topic_id=chunks.topic_id
                          WHERE sources.course_id=%s AND sources.source_id=%s
                          AND sources.owner_student_id=%s AND courses.owner_student_id=%s
                          AND chunks.content IS NOT NULL AND btrim(chunks.content)<>''"""
                scope = (course_id, source_id, owner_student_id, owner_student_id)
                cursor.execute("SELECT " + fields + base + " AND chunks.content ILIKE ANY(%s) ORDER BY length(chunks.content) DESC,chunks.chunk_id LIMIT %s",
                               (*scope, ['%' + term + '%' for term in terms], min(4, limit)))
                hits = cursor.fetchall()
                pages = sorted({row[5] + offset for row in hits if row[5] is not None for offset in (-1, 0, 1) if row[5] + offset > 0})
                slides = sorted({row[6] + offset for row in hits if row[6] is not None for offset in (-1, 0, 1) if row[6] + offset > 0})
                nearby = []
                if hits and (pages or slides):
                    cursor.execute("SELECT " + fields + base + " AND (chunks.page_number=ANY(%s) OR chunks.slide_number=ANY(%s)) ORDER BY length(chunks.content) DESC,chunks.chunk_id LIMIT %s",
                                   (*scope, pages, slides, 6))
                    nearby = cursor.fetchall()
            results, seen = [], set()
            for row in hits + nearby:
                key = ' '.join(row[4].casefold().split())
                if key in seen:
                    continue
                seen.add(key)
                results.append(RetrievedChunk(chunk=Chunk(chunk_id=str(row[0]),source_id=row[1],source_name=row[2],source_type=row[3],content=row[4],page=row[5],slide=row[6],timestamp_start=row[7],timestamp_end=row[8],topic=row[9]),score=0.0))
                if len(results) >= limit:
                    break
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
