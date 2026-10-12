
from pathlib import Path

from backend.ingestion.audio import ingest_audio


audio_path = Path("sample.wav")

if not audio_path.exists():
    raise FileNotFoundError(
        "Place a test audio file named sample.wav "
        "in the project root."
    )

content_units, warnings = ingest_audio(
    data=audio_path.read_bytes(),
    filename=audio_path.name,
)

print("Segments:", len(content_units))
print("Warnings:", warnings)

for unit in content_units:
    print(
        unit["source_location"]["start_seconds"],
        "->",
        unit["source_location"]["end_seconds"],
        ":",
        unit["text"],
    )
