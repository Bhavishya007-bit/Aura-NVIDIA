from backend.ai.ingestion_adapter import (
    convert_ingestion_output
)


# --------------------------------------------------
# Simulated ingestion output
# --------------------------------------------------

ingestion_result = {

    "schema_version": "1.0",

    "source": {
        "filename": "Biochemistry.pdf",
        "file_type": "pdf"
    },

    "status": "success",

    "content_units": [

        {
            "unit_id": "cu_001",

            "source": {
                "filename": "Biochemistry.pdf",
                "file_type": "pdf"
            },

            "text": (
                "ATP synthase produces ATP using "
                "the proton gradient across a membrane."
            ),

            "source_location": {
                "kind": "page",
                "page_number": 142
            },

            "extraction_status": "extracted",

            "warnings": []
        },

        {
            "unit_id": "cu_002",

            "source": {
                "filename": "Biochemistry.pdf",
                "file_type": "pdf"
            },

            "text": (
                "The electron transport chain "
                "transfers electrons and pumps "
                "protons across the membrane."
            ),

            "source_location": {
                "kind": "page",
                "page_number": 143
            },

            "extraction_status": "extracted",

            "warnings": []
        }
    ],

    "warnings": []
}


# --------------------------------------------------
# Convert ingestion output
# --------------------------------------------------

knowledge_units = convert_ingestion_output(
    ingestion_result=ingestion_result,
    source_id=10
)


# --------------------------------------------------
# Display results
# --------------------------------------------------

print("=" * 70)
print("INGESTION ADAPTER TEST")
print("=" * 70)

print(
    f"Knowledge units created: "
    f"{len(knowledge_units)}"
)


for index, unit in enumerate(
    knowledge_units,
    start=1
):

    print("\n" + "-" * 70)

    print(f"Knowledge Unit {index}")

    print("Source ID:", unit.source_id)
    print("Source Type:", unit.source_type)
    print("Source Name:", unit.source_name)
    print("Page:", unit.page)
    print("Slide:", unit.slide)
    print(
        "Timestamp Start:",
        unit.timestamp_start
    )
    print(
        "Timestamp End:",
        unit.timestamp_end
    )
    print("Topic:", unit.topic)

    print("Content:")
    print(unit.content)


# --------------------------------------------------
# Validation
# --------------------------------------------------

assert len(knowledge_units) == 2

assert knowledge_units[0].source_id == 10

assert knowledge_units[0].source_name == (
    "Biochemistry.pdf"
)

assert knowledge_units[0].source_type == "pdf"

assert knowledge_units[0].page == 142

assert knowledge_units[0].content.startswith(
    "ATP synthase"
)

assert knowledge_units[1].page == 143


print("\n" + "=" * 70)
print("INGESTION ADAPTER TEST: PASS")
print("=" * 70)