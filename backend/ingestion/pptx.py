import io
from typing import Any

from pptx import Presentation

from .utils import (
    generate_unit_id,
    has_zip_signature,
)


def ingest_pptx(
    data: bytes,
    filename: str
) -> tuple[list[dict], list[str]]:

    warnings: list[str] = []
    content_units: list[dict] = []

    if not has_zip_signature(data):

        return [], [
            "File does not have a valid Office ZIP signature."
        ]

    try:

        presentation = Presentation(
            io.BytesIO(data)
        )

    except Exception as error:

        return [], [
            f"Failed to open PPTX: {error}"
        ]

    for slide_index, slide in enumerate(
        presentation.slides,
        start=1
    ):

        text_parts: list[str] = []

        for raw_shape in slide.shapes:

            # python-pptx uses different shape classes.
            # Pylance cannot guarantee that every BaseShape
            # has a text attribute, so we treat the shape
            # dynamically here.
            shape: Any = raw_shape

            if not hasattr(shape, "text"):
                continue

            raw_text = shape.text

            if not isinstance(raw_text, str):
                continue

            text = raw_text.strip()

            if text:

                text_parts.append(text)

        slide_text = "\n".join(
            text_parts
        ).strip()

        if not slide_text:

            warnings.append(
                f"Slide {slide_index} "
                f"contains no extractable text."
            )

            continue

        unit_id = generate_unit_id(
            filename,
            "slide",
            str(slide_index)
        )

        content_units.append(
            {
                "unit_id": unit_id,

                "source": {
                    "filename": filename,
                    "file_type": "pptx",
                },

                "text": slide_text,

                "source_location": {
                    "kind": "slide",
                    "slide_number": slide_index,
                },

                "extraction_status": "extracted",

                "warnings": [],
            }
        )

    return content_units, warnings