import io

from .docx import ingest_docx
from .pdf import ingest_pdf
from .pptx import ingest_pptx

from .utils import (
    get_file_type,
    normalize_filename,
    validate_file_size,
    has_mp4_signature,
)


def _build_result(
    filename: str,
    file_type: str,
    status: str,
    content_units: list[dict],
    warnings: list[str]
) -> dict:

    return {
        "schema_version": "1.0",

        "source": {
            "filename": filename,
            "file_type": file_type,
        },

        "status": status,

        "content_units": content_units,

        "warnings": warnings,
    }


def ingest_file(
    file,
    filename: str
) -> dict:
    """
    Main ingestion entry point.

    Parameters
    ----------
    file:
        File-like object or bytes.

    filename:
        Original filename.

    Returns
    -------
    dict
        Standardized ingestion result.
    """

    filename = normalize_filename(
        filename
    )

    file_type = get_file_type(
        filename
    )

    if file_type is None:

        return _build_result(
            filename=filename,
            file_type="unknown",
            status="unsupported",
            content_units=[],
            warnings=[
                "Unsupported file type."
            ]
        )

    try:

        if isinstance(file, bytes):

            data = file

        elif isinstance(file, bytearray):

            data = bytes(file)

        elif hasattr(file, "read"):

            if hasattr(file, "seek"):

                file.seek(0)

            data = file.read()

        else:

            return _build_result(
                filename=filename,
                file_type=file_type,
                status="error",
                content_units=[],
                warnings=[
                    "Input must be bytes or a file-like object."
                ]
            )

    except Exception as error:

        return _build_result(
            filename=filename,
            file_type=file_type,
            status="error",
            content_units=[],
            warnings=[
                f"Failed to read file: {error}"
            ]
        )

    if not isinstance(data, bytes):

        data = bytes(data)

    try:

        validate_file_size(data)

    except ValueError as error:

        return _build_result(
            filename=filename,
            file_type=file_type,
            status="error",
            content_units=[],
            warnings=[str(error)]
        )

    # --------------------------------------------------
    # PDF
    # --------------------------------------------------

    if file_type == "pdf":

        content_units, warnings = ingest_pdf(
            data=data,
            filename=filename
        )

    # --------------------------------------------------
    # PPTX
    # --------------------------------------------------

    elif file_type == "pptx":

        content_units, warnings = ingest_pptx(
            data=data,
            filename=filename
        )

    # --------------------------------------------------
    # DOCX
    # --------------------------------------------------

    elif file_type == "docx":

        content_units, warnings = ingest_docx(
            data=data,
            filename=filename
        )

    # --------------------------------------------------
    # MP4
    # --------------------------------------------------

    elif file_type == "mp4":

        if not has_mp4_signature(data):

            return _build_result(
                filename=filename,
                file_type=file_type,
                status="error",
                content_units=[],
                warnings=[
                    "File does not have a valid MP4 signature."
                ]
            )

        return _build_result(
            filename=filename,
            file_type=file_type,
            status="not_configured",
            content_units=[],
            warnings=[
                "Video transcription provider is not configured."
            ]
        )

    else:

        return _build_result(
            filename=filename,
            file_type=file_type,
            status="unsupported",
            content_units=[],
            warnings=[
                "Unsupported file type."
            ]
        )

    # --------------------------------------------------
    # Determine final status
    # --------------------------------------------------

    if content_units and warnings:

        status = "partial"

    elif content_units:

        status = "success"

    else:

        status = "empty"

    return _build_result(
        filename=filename,
        file_type=file_type,
        status=status,
        content_units=content_units,
        warnings=warnings
    )