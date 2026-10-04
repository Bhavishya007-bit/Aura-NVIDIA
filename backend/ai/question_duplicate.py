from backend.ai.embeddings import EmbeddingModel
from backend.ai.models import MCQ
import numpy as np


class QuestionDuplicateDetector:

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        similarity_threshold: float = 0.90
    ):
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold

        self.questions: list[MCQ] = []
        self.embeddings = None

    def add_question(self, mcq: MCQ):

        question_embedding = self.embedding_model.embed_documents(
            [mcq.question]
        )

        if self.embeddings is None:

            self.embeddings = question_embedding

        else:

            self.embeddings = np.vstack([
                self.embeddings,
                question_embedding
            ])

        self.questions.append(mcq)

    def is_duplicate(self, mcq: MCQ) -> bool:

        if not self.questions:
            return False

        # ========================================================
        # 1. EXACT QUESTION CHECK
        # ========================================================

        new_question = mcq.question.strip().lower()

        for question in self.questions:

            existing_question = (
                question.question.strip().lower()
            )

            if new_question == existing_question:

                print("Exact duplicate question detected.")

                return True

        # ========================================================
        # 2. SEMANTIC SIMILARITY
        # ========================================================

        new_embedding = self.embedding_model.embed_query(
            mcq.question
        )

        similarities = self.embeddings @ new_embedding

        max_similarity = float(similarities.max())

        print(
            f"Maximum question similarity: "
            f"{max_similarity:.4f}"
        )

        # ========================================================
        # 3. TOPIC + ANSWER CHECK
        # ========================================================

        new_topic = (
            mcq.topic.strip().lower()
            if mcq.topic
            else ""
        )

        new_answer = (
            mcq.correct_answer.strip().lower()
        )

        for i, question in enumerate(self.questions):

            existing_topic = (
                question.topic.strip().lower()
                if question.topic
                else ""
            )

            existing_answer = (
                question.correct_answer.strip().lower()
            )

            # ----------------------------------------------------
            # Same topic + same answer + high similarity
            # ----------------------------------------------------

            if (
                new_topic
                and existing_topic
                and new_topic == existing_topic
                and new_answer == existing_answer
                and similarities[i] >= 0.70
            ):

                print(
                    "Duplicate concept detected "
                    "(same topic and correct answer)."
                )

                return True

        # ========================================================
        # 4. GENERAL SEMANTIC DUPLICATE
        # ========================================================

        if max_similarity >= self.similarity_threshold:

            print(
                "Semantic duplicate question detected."
            )

            return True

        return False