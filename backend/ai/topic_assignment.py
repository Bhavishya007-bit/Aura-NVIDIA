import json
import re

from backend.ai.llm import LLM


class TopicAssignment:
    """
    Uses the LLM to identify topics and concepts
    from uploaded course material.
    """

    def __init__(self, llm: LLM | None = None):

        self.llm = (
            llm
            if llm is not None
            else LLM()
        )

    def _extract_json(
        self,
        response: str
    ) -> dict:

        response = response.strip()

        # Remove markdown code fences if the LLM
        # accidentally returns them.

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

    def assign(
        self,
        text: str
    ) -> dict:

        if not text or not text.strip():

            raise ValueError(
                "Text cannot be empty."
            )

        prompt = f"""
You are organizing educational course material.

Analyze the provided material and identify the
main learning topics and concepts contained in it.

Rules:

1. Identify only topics that are actually supported
   by the provided material.

2. Do not introduce unrelated topics.

3. A topic is a broad learning area.

4. A concept is a specific idea, mechanism, process,
   structure, or principle belonging to a topic.

5. Keep topic names concise.

6. Keep concept names concise.

7. Do not provide explanations.

8. Return ONLY valid JSON.

Required JSON format:

{{
    "topics": [
        {{
            "topic_name": "Topic Name",
            "concepts": [
                "Concept 1",
                "Concept 2"
            ]
        }}
    ]
}}

Course material:

{text}
"""

        response = self.llm.generate(prompt)

        data = self._extract_json(response)

        topics = data.get("topics")

        if not isinstance(topics, list):

            raise ValueError(
                "Response must contain a 'topics' list."
            )

        cleaned_topics = []

        for topic in topics:

            if not isinstance(topic, dict):
                continue

            topic_name = topic.get(
                "topic_name"
            )

            concepts = topic.get(
                "concepts",
                []
            )

            if not isinstance(topic_name, str):
                continue

            topic_name = topic_name.strip()

            if not topic_name:
                continue

            if not isinstance(concepts, list):
                concepts = []

            cleaned_concepts = []

            for concept in concepts:

                if not isinstance(
                    concept,
                    str
                ):
                    continue

                concept = concept.strip()

                if not concept:
                    continue

                if concept not in cleaned_concepts:

                    cleaned_concepts.append(
                        concept
                    )

            cleaned_topics.append(
                {
                    "topic_name": topic_name,
                    "concepts": cleaned_concepts,
                }
            )

        if not cleaned_topics:

            raise ValueError(
                "No valid topics were returned."
            )

        return {
            "topics": cleaned_topics
        }