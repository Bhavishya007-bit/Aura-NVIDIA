from backend.ai.models import KnowledgeUnit, MCQ


unit = KnowledgeUnit(
    source_id=1,
    source_type="pdf",
    source_name="Biochemistry.pdf",
    content="ATP synthase is involved in ATP production.",
    page=142
)

print(unit)

mcq = MCQ(
    question="What does ATP synthase use to produce ATP?",
    options=[
        "Proton gradient",
        "DNA replication",
        "Glucose",
        "Oxygen"
    ],
    correct_answer="Proton gradient",
    explanation=(
        "ATP synthase uses the energy from the proton gradient "
        "to produce ATP."
    ),
    topic="Oxidative phosphorylation",
    difficulty="easy",
    source_ids=[1]
)

print("\nMCQ:")
print(mcq)