from backend.ai.citation_grounding import CitationGrounding
from backend.ai.llm import LLM


def main():
    print("=" * 70)
    print("CITATION GROUNDING TEST")
    print("=" * 70)

    llm = LLM()
    verifier = CitationGrounding(llm)

    sources = [
        {
            "source_name": "Biochemistry.pdf",
            "page": 142,
            "content": (
                "ATP synthase is an important enzyme involved in "
                "oxidative phosphorylation. It uses the proton "
                "gradient across the inner mitochondrial membrane. "
                "The movement of protons through ATP synthase "
                "provides energy for ATP production."
            ),
        },
        {
            "source_name": "Biochemistry.pdf",
            "page": 143,
            "content": (
                "The electron transport chain consists of several "
                "protein complexes located in the inner mitochondrial "
                "membrane. These complexes transfer electrons and "
                "use the released energy to pump protons across "
                "the membrane."
            ),
        },
    ]

    # ---------------------------------------------------------
    # TEST 1: Supported claim
    # ---------------------------------------------------------

    answer_1 = (
        "ATP synthase uses the proton gradient to provide "
        "energy for ATP production. [1]"
    )

    print("\nTEST 1: Supported claim")
    print("-" * 70)

    result_1 = verifier.verify_answer(
        answer=answer_1,
        sources=sources,
    )

    print(result_1)

    assert result_1["valid"] is True

    # ---------------------------------------------------------
    # TEST 2: Unsupported claim
    # ---------------------------------------------------------

    answer_2 = (
        "ATP synthase is located inside the nucleus. [1]"
    )

    print("\nTEST 2: Unsupported claim")
    print("-" * 70)

    result_2 = verifier.verify_answer(
        answer=answer_2,
        sources=sources,
    )

    print(result_2)

    assert result_2["valid"] is False

    # ---------------------------------------------------------
    # TEST 3: Multiple supported citations
    # ---------------------------------------------------------

    answer_3 = (
        "ATP synthase uses a proton gradient for ATP production. [1] "
        "The electron transport chain pumps protons across the "
        "membrane. [2]"
    )

    print("\nTEST 3: Multiple supported citations")
    print("-" * 70)

    result_3 = verifier.verify_answer(
        answer=answer_3,
        sources=sources,
    )

    print(result_3)

    assert result_3["valid"] is True

    # ---------------------------------------------------------
    # TEST 4: Invalid citation number
    # ---------------------------------------------------------

    answer_4 = (
        "ATP synthase uses a proton gradient. [3]"
    )

    print("\nTEST 4: Invalid citation number")
    print("-" * 70)

    result_4 = verifier.verify_answer(
        answer=answer_4,
        sources=sources,
    )

    print(result_4)

    assert result_4["valid"] is False

    # ---------------------------------------------------------
    # TEST 5: No citation
    # ---------------------------------------------------------

    answer_5 = (
        "ATP synthase is involved in ATP production."
    )

    print("\nTEST 5: No citation")
    print("-" * 70)

    result_5 = verifier.verify_answer(
        answer=answer_5,
        sources=sources,
    )

    print(result_5)

    assert result_5["valid"] is False

    print("\n" + "=" * 70)
    print("CITATION GROUNDING TEST: PASS")
    print("=" * 70)


if __name__ == "__main__":
    main()