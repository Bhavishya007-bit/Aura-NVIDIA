
import io
import os

from faster_whisper import WhisperModel

from .utils import generate_unit_id


# Configure through environment variables if needed.
MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
MODEL_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
MODEL_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")


_model: WhisperModel | None = None


def get_whisper_model() -> WhisperModel:
    """
    Load the Whisper model only when transcription is requested.
    Reuse the same model for subsequent audio files.
    """
    global _model

    if _model is None:
        _model = WhisperModel(
            MODEL_SIZE,
            device=MODEL_DEVICE,
            compute_type=MODEL_COMPUTE_TYPE,
        )

    return _model


def ingest_audio(
    data: bytes,
    filename: str,
) -> tuple[list[dict], list[str]]:
    """
    Transcribe audio and return standardized content units.

    Each content unit represents one speech segment and
    preserves its start and end timestamps.
    """

    warnings: list[str] = []
    content_units: list[dict] = []

    if not data:
        return [], ["Audio file is empty."]

    try:
        model = get_whisper_model()

        # faster-whisper uses PyAV to decode supported audio formats.
        audio_stream = io.BytesIO(data)

        segments, info = model.transcribe(
            audio_stream,
            beam_size=5,
            vad_filter=False,
            language="en",
        )

        for segment in segments:
            text = segment.text.strip()

            if not text:
                continue

            start = float(segment.start)
            end = float(segment.end)

            # Millisecond precision keeps segment IDs stable.
            location_value = f"{start:.3f}-{end:.3f}"

            unit_id = generate_unit_id(
                filename,
                "segment",
                location_value,
            )

            content_units.append(
                {
                    "unit_id": unit_id,
                    "source": {
                        "filename": filename,
                        "file_type": "audio",
                    },
                    "text": text,
                    "source_location": {
                        "kind": "audio_segment",
                        "start_seconds": start,
                        "end_seconds": end,
                    },
                    "extraction_status": "extracted",
                    "warnings": [],
                }
            )

        if not content_units:
            warnings.append(
                "No speech segments were detected in the audio."
            )

        detected_language = getattr(info, "language", None)

        # Language detection is informational, not a warning.
        # Store it in metadata if needed in a future update.

    except Exception as error:
        return [], [
            f"Audio transcription failed: {error}"
        ]

    return content_units, warnings
