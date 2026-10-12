
import hashlib
from pathlib import Path


MAX_FILE_SIZE = 100 * 1024 * 1024


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".ppt",
    ".pptx",
    ".docx",
    ".mp4",
    ".mp3",
    ".wav",
    ".m4a",
    ".ogg",
    ".flac",
    ".aac",
    ".webm",
    ".mpeg",
    ".mpga",
}


def normalize_filename(filename: str) -> str:
    """
    Return a safe filename string.
    """

    if not filename:
        return "unknown"

    return Path(filename).name



def get_file_type(filename: str) -> str | None:
    extension = Path(filename).suffix.lower()

    mapping = {
        ".pdf": "pdf",
        # Converted by ingest_pptx; use the existing presentation source type.
        ".ppt": "pptx",
        ".pptx": "pptx",
        ".docx": "docx",
        ".mp4": "mp4",
        ".mp3": "audio",
        ".wav": "audio",
        ".m4a": "audio",
        ".ogg": "audio",
        ".flac": "audio",
        ".aac": "audio",
        ".webm": "webm",
        ".mpeg": "audio",
        ".mpga": "audio",
    }

    return mapping.get(extension)



def validate_file_size(data: bytes) -> None:
    """
    Reject files larger than 100 MiB.
    """

    if len(data) > MAX_FILE_SIZE:
        raise ValueError(
            "File exceeds the maximum allowed size of 100 MiB."
        )


def generate_unit_id(
    filename: str,
    location_key: str,
    location_value: str,
) -> str:
    """
    Generate a deterministic content-unit ID.

    The same filename + location produces
    the same ID.
    """

    raw = (
        f"{filename}|"
        f"{location_key}|"
        f"{location_value}"
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:16]

    return f"cu_{digest}"


def has_pdf_signature(data: bytes) -> bool:
    """
    Check for the PDF file signature.
    """

    return data.startswith(b"%PDF-")


def has_zip_signature(data: bytes) -> bool:
    """
    PPTX and DOCX are ZIP-based Office files.
    """

    return data.startswith(
        (
            b"PK\x03\x04",
            b"PK\x05\x06",
            b"PK\x07\x08",
        )
    )


def has_mp4_signature(data: bytes) -> bool:
    """
    Basic MP4 container check.

    MP4 files normally contain 'ftyp'
    at byte offset 4.
    """

    return (
        len(data) >= 8
        and data[4:8] == b"ftyp"
    )
