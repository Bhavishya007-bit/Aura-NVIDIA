import io

import pymupdf

from .utils import (
    generate_unit_id,
    has_pdf_signature,
)


def ingest_pdf(
    data: bytes,
    filename: str
) -> tuple[list[dict], list[str]]:

    warnings: list[str] = []
    content_units: list[dict] = []

    if not has_pdf_signature(data):

        return [], [
            "File does not have a valid PDF signature."
        ]

    try:

        document = pymupdf.open(
            stream=io.BytesIO(data),
            filetype="pdf"
        )

    except Exception as error:

        return [], [
            f"Failed to open PDF: {error}"
        ]

    try:

        for page_index in range(len(document)):

            page_number = page_index + 1

            try:

                page = document.load_page(
                    page_index
                )

                raw_text = page.get_text(
                    "text"
                )

                if isinstance(raw_text, str):

                    text = raw_text.strip()

                else:

                    text = str(raw_text).strip()

            except Exception as error:

                warnings.append(
                    f"Failed to extract page "
                    f"{page_number}: {error}"
                )

                continue

            if not text:

                warnings.append(
                    f"Page {page_number} "
                    f"contains no extractable text."
                )

                continue

            unit_id = generate_unit_id(
                filename,
                "page",
                str(page_number)
            )

            content_units.append(
                {
                    "unit_id": unit_id,

                    "source": {
                        "filename": filename,
                        "file_type": "pdf",
                    },

                    "text": text,

                    "source_location": {
                        "kind": "page",
                        "page_number": page_number,
                    },

                    "extraction_status": "extracted",

                    "warnings": [],
                }
            )

    finally:

        document.close()

    return content_units, warnings