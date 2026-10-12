
from pathlib import Path

from backend.ingestion.ingest import ingest_file


docx_path = Path("test_assets/sample.docx")

result = ingest_file(
    file=docx_path.read_bytes(),
    filename=docx_path.name,
)

print("Status:", result["status"])
print("Source:", result["source"])
print("Warnings:", result["warnings"])
print("Content units:", len(result["content_units"]))

for unit in result["content_units"]:
    print("Location:", unit["source_location"])
    print("Text:", unit["text"])
    print("-" * 40)
