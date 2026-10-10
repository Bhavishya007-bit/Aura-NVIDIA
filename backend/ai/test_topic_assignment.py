from backend.ai.topic_assignment import TopicAssignment


def main():

    print("\n")
    print("=" * 70)
    print("TOPIC ASSIGNMENT TEST")
    print("=" * 70)

    # --------------------------------------------------
    # Test material
    # --------------------------------------------------

    text = """
    Oxidative phosphorylation is the final stage of
    cellular respiration. Electrons pass through the
    electron transport chain located in the inner
    mitochondrial membrane. The energy released during
    electron transfer is used to pump protons across
    the membrane, creating a proton gradient.

    ATP synthase uses the proton gradient to produce ATP.
    Protons flow through ATP synthase, causing rotational
    movement that drives ATP synthesis.
    """

    # --------------------------------------------------
    # Create topic assignment system
    # --------------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 1: CREATE TOPIC ASSIGNMENT")
    print("=" * 70)

    topic_assignment = TopicAssignment()

    print(
        "Topic assignment system created."
    )

    # --------------------------------------------------
    # Assign topics
    # --------------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 2: ASSIGN TOPICS AND CONCEPTS")
    print("=" * 70)

    result = topic_assignment.assign(
        text=text
    )

    print("\nResult:")
    print(result)

    # --------------------------------------------------
    # Validate result
    # --------------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 3: VALIDATE RESULT")
    print("=" * 70)

    assert isinstance(
        result,
        dict
    )

    assert "topics" in result

    assert isinstance(
        result["topics"],
        list
    )

    assert len(
        result["topics"]
    ) > 0

    for topic in result["topics"]:

        assert isinstance(
            topic,
            dict
        )

        assert "topic_name" in topic

        assert "concepts" in topic

        assert isinstance(
            topic["topic_name"],
            str
        )

        assert topic["topic_name"].strip()

        assert isinstance(
            topic["concepts"],
            list
        )

        for concept in topic["concepts"]:

            assert isinstance(
                concept,
                str
            )

            assert concept.strip()

    # --------------------------------------------------
    # Display topics
    # --------------------------------------------------

    print("\n")
    print("=" * 70)
    print("EXTRACTED TOPICS")
    print("=" * 70)

    for topic in result["topics"]:

        print(
            f"\nTopic: {topic['topic_name']}"
        )

        print("Concepts:")

        for concept in topic["concepts"]:

            print(
                f"  - {concept}"
            )

    # --------------------------------------------------
    # Final
    # --------------------------------------------------

    print("\n")
    print("=" * 70)
    print("TOPIC ASSIGNMENT TEST: PASS")
    print("=" * 70)


if __name__ == "__main__":

    main()