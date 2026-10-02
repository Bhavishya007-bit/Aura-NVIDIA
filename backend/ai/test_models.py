from models import KnowledgeUnit


unit = KnowledgeUnit(
    source_id=1,
    source_type="pdf",
    source_name="Biochemistry.pdf",
    content="ATP synthase is involved in ATP production.",
    page=142
)

print(unit)