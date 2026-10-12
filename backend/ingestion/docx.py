
import io

from docx import Document

from .utils import (
    generate_unit_id,
    has_zip_signature,
)


def ingest_docx(
    data: bytes,
    filename: str,
) -> tuple[list[dict], list[str]]:

    warnings: list[str] = []
    content_units: list[dict] = []

    if not has_zip_signature(data):
        return [], [
            "File does not have a valid Office ZIP signature."
        ]

    try:
        document = Document(io.BytesIO(data))
    except Exception as error:
        return [], [f"Failed to open DOCX: {error}"]

    paragraph_index = 0

    # Extract regular paragraphs.
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()

        if not text:
            continue

        paragraph_index += 1

        unit_id = generate_unit_id(
            filename,
            "paragraph",
            str(paragraph_index),
        )

        content_units.append({
            "unit_id": unit_id,
            "source": {
                "filename": filename,
                "file_type": "docx",
            },
            "text": text,
            "source_location": {
                "kind": "paragraph",
                "paragraph_number": paragraph_index,
            },
            "extraction_status": "extracted",
            "warnings": [],
        })

    # Extract tables, preserving their row and column positions.
    table_count = 0

    for table_index, table in enumerate(document.tables, start=1):
        for row_index, row in enumerate(table.rows, start=1):
            for column_index, cell in enumerate(row.cells, start=1):
                text = cell.text.strip()

                if not text:
                    continue

                table_count += 1

                unit_id = generate_unit_id(
                    filename,
                    "table_cell",
                    f"{table_index}-{row_index}-{column_index}",
                )

                content_units.append({
                    "unit_id": unit_id,
                    "source": {
                        "filename": filename,
                        "file_type": "docx",
                    },
                    "text": text,
                    "source_location": {
                        "kind": "table_cell",
                        "table_number": table_index,
                        "row_number": row_index,
                        "column_number": column_index,
                    },
                    "extraction_status": "extracted",
                    "warnings": [],
                })

    if not content_units:
        warnings.append(
            "DOCX contains no non-empty paragraphs or table cells."
        )

    return content_units, warnings
