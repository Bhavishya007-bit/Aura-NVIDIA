from backend.ai.citation_validator import CitationValidator


def main():
    validator = CitationValidator()

    print("=" * 70)
    print("CITATION VALIDATOR TEST")
    print("=" * 70)

    # ---------------------------------------------------------
    # TEST 1: Valid citations
    # ---------------------------------------------------------

    answer_1 = (
        "ATP synthase uses the proton gradient to produce ATP [1]. "
        "The electron transport chain creates this proton gradient [2]."
    )

    result_1 = validator.validate(
        answer=answer_1,
        number_of_sources=2,
    )

    print("\nTEST 1: Valid citations")
    print("-" * 70)
    print(result_1)

    assert result_1["valid"] is True
    assert result_1["citations"] == [1, 2]
    assert result_1["invalid_citations"] == []

    # ---------------------------------------------------------
    # TEST 2: Invalid citation
    # ---------------------------------------------------------

    answer_2 = (
        "ATP synthase uses the proton gradient to produce ATP [1]. "
        "This process occurs in mitochondria [3]."
    )

    result_2 = validator.validate(
        answer=answer_2,
        number_of_sources=2,
    )

    print("\nTEST 2: Invalid citation")
    print("-" * 70)
    print(result_2)

    assert result_2["valid"] is False
    assert result_2["invalid_citations"] == [3]

    # ---------------------------------------------------------
    # TEST 3: Duplicate citations
    # ---------------------------------------------------------

    answer_3 = (
        "ATP synthase uses a proton gradient [1]. "
        "The proton gradient provides energy [1]."
    )

    result_3 = validator.validate(
        answer=answer_3,
        number_of_sources=1,
    )

    print("\nTEST 3: Duplicate citations")
    print("-" * 70)
    print(result_3)

    assert result_3["valid"] is True
    assert result_3["citations"] == [1]

    # ---------------------------------------------------------
    # TEST 4: No citations
    # ---------------------------------------------------------

    answer_4 = (
        "ATP synthase is involved in ATP production."
    )

    result_4 = validator.validate(
        answer=answer_4,
        number_of_sources=2,
    )

    print("\nTEST 4: No citations")
    print("-" * 70)
    print(result_4)

    # No citation is not considered an invalid citation.
    # The current validator only validates citation numbers.
    assert result_4["valid"] is True
    assert result_4["citations"] == []

    # ---------------------------------------------------------
    # TEST 5: Empty answer
    # ---------------------------------------------------------

    result_5 = validator.validate(
        answer="",
        number_of_sources=2,
    )

    print("\nTEST 5: Empty answer")
    print("-" * 70)
    print(result_5)

    assert result_5["valid"] is False

    print("\n" + "=" * 70)
    print("CITATION VALIDATOR TEST: PASS")
    print("=" * 70)


if __name__ == "__main__":
    main()