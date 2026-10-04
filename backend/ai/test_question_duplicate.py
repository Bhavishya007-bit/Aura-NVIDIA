from backend.ai.embeddings import EmbeddingModel
from backend.ai.models import MCQ
from backend.ai.question_duplicate import QuestionDuplicateDetector


embedding_model = EmbeddingModel()

detector = QuestionDuplicateDetector(
    embedding_model=embedding_model,
    similarity_threshold=0.80
)


mcq1 = MCQ(
    question="What provides energy for ATP production?",
    options=[
        "Proton movement",
        "DNA replication",
        "Glucose",
        "Oxygen"
    ],
    correct_answer="Proton movement",
    explanation="Proton movement provides energy for ATP production.",
    topic="ATP synthase",
    difficulty="easy",
    source_ids=[1]
)


mcq2 = MCQ(
    question="What provides energy for ATP production?",
    options=[
        "Proton movement",
        "DNA replication",
        "Glucose",
        "Oxygen"
    ],
    correct_answer="Proton movement",
    explanation="Proton movement provides energy for ATP production.",
    topic="ATP synthase",
    difficulty="easy",
    source_ids=[1]
)


mcq3 = MCQ(
    question="What supplies the energy required to produce ATP?",
    options=[
        "Proton movement",
        "DNA replication",
        "Glucose",
        "Oxygen"
    ],
    correct_answer="Proton movement",
    explanation="Proton movement provides energy for ATP production.",
    topic="ATP synthase",
    difficulty="easy",
    source_ids=[1]
)


mcq4 = MCQ(
    question="What protein complexes are involved in the electron transport chain?",
    options=[
        "Protein complexes in the inner mitochondrial membrane",
        "Ribosomes",
        "DNA polymerase",
        "ATP synthase"
    ],
    correct_answer="Protein complexes in the inner mitochondrial membrane",
    explanation="The electron transport chain consists of several protein complexes.",
    topic="Electron transport chain",
    difficulty="easy",
    source_ids=[1]
)


# Add the first question to our database
detector.add_question(mcq1)


print("\nQuestion 2:")
print("Duplicate:", detector.is_duplicate(mcq2))

print("\nQuestion 3:")
print("Duplicate:", detector.is_duplicate(mcq3))

print("\nQuestion 4:")
print("Duplicate:", detector.is_duplicate(mcq4))