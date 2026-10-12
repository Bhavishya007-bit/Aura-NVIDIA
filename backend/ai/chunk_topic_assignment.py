import json
import re

from backend.ai.llm import LLM


class ChunkTopicAssignment:
    """
    Assigns each chunk to an existing topic and concept.

    The LLM is only allowed to choose from the
    provided topics and concepts.
    """

    def __init__(self, llm: LLM | None = None):

        self.llm = (
            llm
            if llm is not None
            else LLM()
        )

    # ==================================================
    # EXTRACT JSON
    # ==================================================

    def _extract_json(
        self,
        response: str
    ) -> dict:

        response = response.strip()

        # Remove markdown code fences if present.

        response = re.sub(
            r"^```(?:json)?\s*",
            "",
            response,
            flags=re.IGNORECASE
        )

        response = re.sub(
            r"\s*```$",
            "",
            response
        )

        try:

            data = json.loads(response)

        except json.JSONDecodeError as error:

            raise ValueError(
                f"LLM returned invalid JSON: {error}"
            ) from error

        if not isinstance(data, dict):

            raise ValueError(
                "LLM response must be a JSON object."
            )

        return data

    # ==================================================
    # BUILD AVAILABLE KNOWLEDGE
    # ==================================================

    def _build_topic_text(
        self,
        topics: list[dict]
    ) -> str:

        lines = []

        for topic in topics:

            topic_name = topic.get(
                "topic_name"
            )

            concepts = topic.get(
                "concepts",
                []
            )

            if not isinstance(
                topic_name,
                str
            ):
                continue

            topic_name = topic_name.strip()

            if not topic_name:
                continue

            lines.append(
                f"Topic: {topic_name}"
            )

            for concept in concepts:

                if not isinstance(
                    concept,
                    str
                ):
                    continue

                concept = concept.strip()

                if not concept:
                    continue

                lines.append(
                    f"  Concept: {concept}"
                )

        return "\n".join(lines)

    # ==================================================
    # VALIDATE TOPICS
    # ==================================================

    def _build_valid_topic_map(
        self,
        topics: list[dict]
    ) -> dict:

        valid_topics = {}

        for topic in topics:

            if not isinstance(
                topic,
                dict
            ):
                continue

            topic_name = topic.get(
                "topic_name"
            )

            concepts = topic.get(
                "concepts",
                []
            )

            if not isinstance(
                topic_name,
                str
            ):
                continue

            topic_name = topic_name.strip()

            if not topic_name:
                continue

            concept_map = {}

            if isinstance(concepts, list):

                for concept in concepts:

                    if not isinstance(
                        concept,
                        str
                    ):
                        continue

                    concept = concept.strip()

                    if not concept:
                        continue

                    concept_map[
                        concept.lower()
                    ] = concept

            valid_topics[
                topic_name.lower()
            ] = {
                "topic_name": topic_name,
                "concepts": concept_map,
            }

        return valid_topics

    # ==================================================
    # ASSIGN CHUNKS
    # ==================================================

    def assign(
        self,
        chunks: list[dict],
        topics: list[dict]
    ) -> dict:

        if not chunks:

            raise ValueError(
                "Chunks cannot be empty."
            )

        if not topics:

            raise ValueError(
                "Topics cannot be empty."
            )

        topic_map = self._build_valid_topic_map(
            topics
        )

        if not topic_map:

            raise ValueError(
                "No valid topics were provided."
            )

        available_topics = (
            self._build_topic_text(topics)
        )

        chunk_lines = []

        for chunk in chunks:

            chunk_id = chunk.get(
                "chunk_id"
            )

            content = chunk.get(
                "content",
                ""
            )

            if chunk_id is None:

                raise ValueError(
                    "Every chunk must contain "
                    "a chunk_id."
                )

            if not isinstance(
                content,
                str
            ):

                raise ValueError(
                    f"Chunk {chunk_id} content "
                    "must be a string."
                )

            content = content.strip()

            if not content:

                continue

            chunk_lines.append(
                f"Chunk ID: {chunk_id}\n"
                f"Content: {content}"
            )

        if not chunk_lines:

            raise ValueError(
                "No valid chunk content was provided."
            )

        chunks_text = "\n\n".join(
            chunk_lines
        )

        # ==================================================
        # LLM PROMPT
        # ==================================================

        prompt = f"""
You are assigning educational content chunks
to an existing course topic and concept hierarchy.

You MUST choose the topic and concept ONLY from
the provided list.

Do NOT create new topics.

Do NOT create new concepts.

Do NOT rename topics.

Do NOT rename concepts.

Each chunk should be assigned to the topic and
concept that best matches its actual content.

If a chunk does not contain enough information to
reliably identify a concept, use null for concept_name.

The topic must still be selected when the chunk
clearly belongs to one of the provided topics.

Return ONLY valid JSON.

Required format:

{{
    "assignments": [
        {{
            "chunk_id": 13,
            "topic_name": "Oxidative Phosphorylation",
            "concept_name": "ATP Synthase"
        }}
    ]
}}

Available topics and concepts:

{available_topics}

Chunks:

{chunks_text}
"""

        response = self.llm.generate(
            prompt
        )

        data = self._extract_json(
            response
        )

        assignments = data.get(
            "assignments"
        )

        if not isinstance(
            assignments,
            list
        ):

            raise ValueError(
                "Response must contain "
                "an 'assignments' list."
            )

        # ==================================================
        # VALIDATE ASSIGNMENTS
        # ==================================================

        valid_chunk_ids = {
            chunk.get("chunk_id")
            for chunk in chunks
            if chunk.get("chunk_id") is not None
        }

        cleaned_assignments = []

        assigned_chunk_ids = set()

        for assignment in assignments:

            if not isinstance(
                assignment,
                dict
            ):
                continue

            chunk_id = assignment.get(
                "chunk_id"
            )

            topic_name = assignment.get(
                "topic_name"
            )

            concept_name = assignment.get(
                "concept_name"
            )

            # ----------------------------------------------
            # Validate chunk ID
            # ----------------------------------------------

            if chunk_id not in valid_chunk_ids:

                continue

            # ----------------------------------------------
            # Prevent duplicate assignments
            # ----------------------------------------------

            if chunk_id in assigned_chunk_ids:

                continue

            # ----------------------------------------------
            # Validate topic
            # ----------------------------------------------

            if not isinstance(
                topic_name,
                str
            ):
                continue

            topic_name = topic_name.strip()

            topic_info = topic_map.get(
                topic_name.lower()
            )

            if topic_info is None:

                continue

            canonical_topic_name = (
                topic_info["topic_name"]
            )

            # ----------------------------------------------
            # Validate concept
            # ----------------------------------------------

            canonical_concept_name = None

            if concept_name is not None:

                if not isinstance(
                    concept_name,
                    str
                ):
                    continue

                concept_name = concept_name.strip()

                if concept_name:

                    canonical_concept_name = (
                        topic_info["concepts"].get(
                            concept_name.lower()
                        )
                    )

                    if canonical_concept_name is None:

                        continue

            cleaned_assignments.append(
                {
                    "chunk_id": chunk_id,
                    "topic_name": canonical_topic_name,
                    "concept_name": canonical_concept_name,
                }
            )

            assigned_chunk_ids.add(
                chunk_id
            )

        return {
            "assignments": cleaned_assignments
        }