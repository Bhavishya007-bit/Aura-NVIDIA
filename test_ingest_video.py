
from pathlib import Path

from backend.ingestion.ingest import ingest_file


video_path = Path("test_assets/sample.mp4")

if not video_path.exists():
    raise FileNotFoundError(f"Video not found: {video_path}")

result = ingest_file(
    file=video_path.read_bytes(),
    filename=video_path.name,
)

print("Status:", result["status"])
print("Source:", result["source"])
print("Warnings:", result["warnings"])
print("Content units:", len(result["content_units"]))

for unit in result["content_units"]:
    print("Location:", unit["source_location"])
    print("Transcript:", unit["text"])
