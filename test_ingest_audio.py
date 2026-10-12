
from pathlib import Path

from backend.ingestion.ingest import ingest_file


audio_path = Path("sample.wav")

if not audio_path.exists():
    raise FileNotFoundError(
        "Place sample.wav in the project root."
    )

result = ingest_file(
    file=audio_path.read_bytes(),
    filename=audio_path.name,
)

print("Status:", result["status"])
print("Source:", result["source"])
print("Warnings:", result["warnings"])
print("Content units:", len(result["content_units"]))

for unit in result["content_units"]:
    print(unit["source_location"], unit["text"])
