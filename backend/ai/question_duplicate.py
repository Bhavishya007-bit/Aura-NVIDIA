from backend.ai.embeddings import EmbeddingModel
from backend.ai.models import MCQ


class QuestionDuplicateDetector:

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        similarity_threshold: float = 0.80
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
            import numpy as np

            self.embeddings = np.vstack([
                self.embeddings,
                question_embedding
            ])

        self.questions.append(mcq)

    def is_duplicate(self, mcq: MCQ) -> bool:

        if not self.questions:
            return False

        # First: exact duplicate check
        new_question = mcq.question.strip().lower()

        for question in self.questions:
            existing_question = question.question.strip().lower()

            if new_question == existing_question:
                return True

        # Second: semantic similarity
        new_embedding = self.embedding_model.embed_query(
            mcq.question
        )

        similarities = self.embeddings @ new_embedding

        max_similarity = similarities.max()

        print(f"Maximum similarity: {max_similarity:.4f}")

        return max_similarity >= self.similarity_threshold