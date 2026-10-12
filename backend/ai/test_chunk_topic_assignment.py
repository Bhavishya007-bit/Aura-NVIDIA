from backend.ai.chunk_topic_assignment import ChunkTopicAssignment


def main():

    print("\n")
    print("=" * 70)
    print("CHUNK TOPIC ASSIGNMENT TEST")
    print("=" * 70)

    # ==================================================
    # TEST TOPICS AND CONCEPTS
    # ==================================================

    topics = [
        {
            "topic_name": "Oxidative Phosphorylation",
            "concepts": [
                "Electron Transport Chain",
                "Proton Gradient",
                "ATP Synthase",
            ],
        }
    ]

    # ==================================================
    # TEST CHUNKS
    # ==================================================

    chunks = [
        {
            "chunk_id": 13,
            "content": (
                "ATP synthase is an enzyme that produces ATP "
                "using the proton gradient across a membrane. "
                "Protons move through ATP synthase and the "
                "energy released drives ATP production."
            ),
        },
        {
            "chunk_id": 14,
            "content": (
                "The electron transport chain consists of "
                "protein complexes in the inner mitochondrial "
                "membrane. These complexes transfer electrons "
                "and pump protons across the membrane."
            ),
        },
    ]

    # ==================================================
    # STEP 1: CREATE ASSIGNMENT SYSTEM
    # ==================================================

    print("\n")
    print("=" * 70)
    print("STEP 1: CREATE CHUNK TOPIC ASSIGNMENT")
    print("=" * 70)

    assignment_system = ChunkTopicAssignment()

    print(
        "Chunk topic assignment system created."
    )

    # ==================================================
    # STEP 2: ASSIGN CHUNKS
    # ==================================================

    print("\n")
    print("=" * 70)
    print("STEP 2: ASSIGN CHUNKS")
    print("=" * 70)

    result = assignment_system.assign(
        chunks=chunks,
        topics=topics,
    )

    print("\nResult:")
    print(result)

    # ==================================================
    # STEP 3: VALIDATE RESULT STRUCTURE
    # ==================================================

    print("\n")
    print("=" * 70)
    print("STEP 3: VALIDATE RESULT")
    print("=" * 70)

    assert isinstance(
        result,
        dict
    )

    assert "assignments" in result

    assignments = result["assignments"]

    assert isinstance(
        assignments,
        list
    )

    assert len(assignments) > 0

    # ==================================================
    # STEP 4: VALIDATE EACH ASSIGNMENT
    # ==================================================

    valid_chunk_ids = {
        13,
        14,
    }

    valid_topic = (
        "Oxidative Phosphorylation"
    )

    valid_concepts = {
        "Electron Transport Chain",
        "Proton Gradient",
        "ATP Synthase",
    }

    assigned_chunk_ids = set()

    for assignment in assignments:

        assert isinstance(
            assignment,
            dict
        )

        assert "chunk_id" in assignment

        assert "topic_name" in assignment

        assert "concept_name" in assignment

        chunk_id = assignment["chunk_id"]

        topic_name = assignment["topic_name"]

        concept_name = assignment["concept_name"]

        # ----------------------------------------------
        # Chunk validation
        # ----------------------------------------------

        assert chunk_id in valid_chunk_ids

        assert chunk_id not in assigned_chunk_ids

        assigned_chunk_ids.add(
            chunk_id
        )

        # ----------------------------------------------
        # Topic validation
        # ----------------------------------------------

        assert (
            topic_name
            == valid_topic
        )

        # ----------------------------------------------
        # Concept validation
        # ----------------------------------------------

        if concept_name is not None:

            assert (
                concept_name
                in valid_concepts
            )

    # ==================================================
    # STEP 5: DISPLAY ASSIGNMENTS
    # ==================================================

    print("\n")
    print("=" * 70)
    print("CHUNK ASSIGNMENTS")
    print("=" * 70)

    for assignment in assignments:

        print(
            f"\nChunk ID: "
            f"{assignment['chunk_id']}"
        )

        print(
            f"Topic: "
            f"{assignment['topic_name']}"
        )

        print(
            f"Concept: "
            f"{assignment['concept_name']}"
        )

    # ==================================================
    # STEP 6: CHECK EXPECTED CONCEPTS
    # ==================================================

    assignment_map = {
        assignment["chunk_id"]: assignment
        for assignment in assignments
    }

    if 13 in assignment_map:

        assert (
            assignment_map[13]["concept_name"]
            == "ATP Synthase"
        )

    if 14 in assignment_map:

        assert (
            assignment_map[14]["concept_name"]
            == "Electron Transport Chain"
        )

    # ==================================================
    # FINAL
    # ==================================================

    print("\n")
    print("=" * 70)
    print("CHUNK TOPIC ASSIGNMENT TEST: PASS")
    print("=" * 70)


if __name__ == "__main__":

    main()