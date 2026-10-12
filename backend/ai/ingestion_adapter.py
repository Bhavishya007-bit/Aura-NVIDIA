from backend.ai.models import KnowledgeUnit


def convert_ingestion_output(
    ingestion_result: dict,
    source_id: int
) -> list[KnowledgeUnit]:
    """
    Convert the teammate's ingestion output into
    AI-layer KnowledgeUnit objects.

    The ingestion layer is responsible for extracting
    content and source locations.

    The AI layer starts from KnowledgeUnit.
    """

    knowledge_units = []

    source = ingestion_result.get("source", {})

    source_name = source.get("filename", "unknown")
    source_type = source.get("file_type", "unknown")

    content_units = ingestion_result.get(
        "content_units",
        []
    )

    for content_unit in content_units:

        text = content_unit.get("text", "").strip()

        if not text:
            continue

        location = content_unit.get(
            "source_location",
            {}
        )

        location_kind = location.get("kind")

        page = None
        slide = None
        timestamp_start = None
        timestamp_end = None

        # -------------------------------
        # PDF
        # -------------------------------

        if location_kind == "page":

            page = location.get(
                "page_number"
            )

        # -------------------------------
        # PPTX
        # -------------------------------

        elif location_kind == "slide":

            slide = location.get(
                "slide_number"
            )

        # -------------------------------
        # Video
        # -------------------------------

        elif location_kind == "timestamp":

            timestamp_start = location.get(
                "timestamp_start"
            )

            timestamp_end = location.get(
                "timestamp_end"
            )

        knowledge_unit = KnowledgeUnit(
            source_id=source_id,
            source_type=source_type,
            source_name=source_name,
            content=text,
            page=page,
            slide=slide,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            topic=None
        )

        knowledge_units.append(
            knowledge_unit
        )

    return knowledge_units