import io

from docx import Document

from .utils import (
    generate_unit_id,
    has_zip_signature,
)


def ingest_docx(
    data: bytes,
    filename: str
) -> tuple[list[dict], list[str]]:

    warnings = []
    content_units = []

    if not has_zip_signature(data):

        return [], [
            "File does not have a valid Office ZIP signature."
        ]

    try:

        document = Document(
            io.BytesIO(data)
        )

    except Exception as error:

        return [], [
            f"Failed to open DOCX: {error}"
        ]

    paragraph_index = 0

    for paragraph in document.paragraphs:

        text = paragraph.text.strip()

        if not text:
            continue

        paragraph_index += 1

        unit_id = generate_unit_id(
            filename,
            "paragraph",
            str(paragraph_index)
        )

        content_units.append(
            {
                "unit_id": unit_id,

                "source": {
                    "filename": filename,
                    "file_type": "docx",
                },

                "text": text,

                # We intentionally do not invent
                # DOCX page numbers.
                "source_location": {
                    "kind": "paragraph",
                    "paragraph_number": paragraph_index,
                },

                "extraction_status": "extracted",

                "warnings": [],
            }
        )

    if not content_units:

        warnings.append(
            "DOCX contains no non-empty body paragraphs."
        )

    return content_units, warnings