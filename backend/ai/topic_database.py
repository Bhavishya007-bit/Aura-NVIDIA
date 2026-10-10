import os

import psycopg2
from dotenv import load_dotenv

load_dotenv("backend/.env")


class TopicDatabase:
    """
    Handles storing topics and concepts in PostgreSQL.
    """

    def __init__(self):

        self.connection = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
        )

    def store_topics(
        self,
        course_id: int,
        topic_data: dict,
    ) -> list[dict]:
        """
        Store topics and their concepts for a course.

        Returns:

        [
            {
                "topic_id": 1,
                "topic_name": "Oxidative Phosphorylation",
                "concepts": [
                    {
                        "concept_id": 1,
                        "concept_name": "ATP Synthase"
                    }
                ]
            }
        ]
        """

        if not isinstance(topic_data, dict):

            raise ValueError(
                "topic_data must be a dictionary."
            )

        topics = topic_data.get("topics")

        if not isinstance(topics, list):

            raise ValueError(
                "topic_data must contain a 'topics' list."
            )

        cursor = self.connection.cursor()

        stored_topics = []

        try:

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

                if not isinstance(
                    topic_name,
                    str
                ):
                    continue

                topic_name = topic_name.strip()

                if not topic_name:
                    continue

                if not isinstance(
                    concepts,
                    list
                ):
                    concepts = []

                # --------------------------------------
                # Check whether topic already exists
                # --------------------------------------

                cursor.execute(
                    """
                    SELECT topic_id
                    FROM topics
                    WHERE course_id = %s
                      AND LOWER(topic_name) = LOWER(%s)
                    LIMIT 1;
                    """,
                    (
                        course_id,
                        topic_name,
                    )
                )

                row = cursor.fetchone()

                if row is not None:

                    topic_id = row[0]

                else:

                    # ----------------------------------
                    # Create topic
                    # ----------------------------------

                    cursor.execute(
                        """
                        INSERT INTO topics (
                            course_id,
                            topic_name
                        )
                        VALUES (%s, %s)
                        RETURNING topic_id;
                        """,
                        (
                            course_id,
                            topic_name,
                        )
                    )

                    row = cursor.fetchone()

                    if row is None:

                        raise RuntimeError(
                            "Failed to create topic."
                        )

                    topic_id = row[0]

                stored_concepts = []

                # --------------------------------------
                # Store concepts
                # --------------------------------------

                for concept in concepts:

                    if not isinstance(
                        concept,
                        str
                    ):
                        continue

                    concept_name = concept.strip()

                    if not concept_name:
                        continue

                    # ----------------------------------
                    # Check whether concept exists
                    # ----------------------------------

                    cursor.execute(
                        """
                        SELECT concept_id
                        FROM concepts
                        WHERE topic_id = %s
                          AND LOWER(concept_name) = LOWER(%s)
                        LIMIT 1;
                        """,
                        (
                            topic_id,
                            concept_name,
                        )
                    )

                    row = cursor.fetchone()

                    if row is not None:

                        concept_id = row[0]

                    else:

                        # ------------------------------
                        # Create concept
                        # ------------------------------

                        cursor.execute(
                            """
                            INSERT INTO concepts (
                                topic_id,
                                concept_name
                            )
                            VALUES (%s, %s)
                            RETURNING concept_id;
                            """,
                            (
                                topic_id,
                                concept_name,
                            )
                        )

                        row = cursor.fetchone()

                        if row is None:

                            raise RuntimeError(
                                "Failed to create concept."
                            )

                        concept_id = row[0]

                    stored_concepts.append(
                        {
                            "concept_id": concept_id,
                            "concept_name": concept_name,
                        }
                    )

                stored_topics.append(
                    {
                        "topic_id": topic_id,
                        "topic_name": topic_name,
                        "concepts": stored_concepts,
                    }
                )

            self.connection.commit()

            return stored_topics

        except Exception:

            self.connection.rollback()

            raise

        finally:

            cursor.close()

    def close(self):

        self.connection.close()