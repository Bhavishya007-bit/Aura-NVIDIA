"""Conservative checks for two observed teaching-verifier false acceptances.

These recognise limited English forms, not arbitrary factual correctness. They
only reject or request correction; they never rewrite an answer or approve it.
"""

import re


def plain(text):
    return " ".join(re.sub(r"[*_`]", "", text).casefold().split())


def sentences(text):
    return [plain(s).strip(' \t.!?;:"“”') for s in re.split(r"(?<=[.!?])\s+|\n+", text)]


EFFECT = re.compile(
    r"\b(?:affects?|influenc\w*|impacts?|increas\w*|decreas\w*|reduc\w*|improv\w*|degrad\w*|determin\w*|leads?|results?)\b"
)
OUTCOME = re.compile(
    r"\b(?:collisions?|performance|probes?|probing|complexity|speed|lookup|search)\b"
)
DEFINITION = re.compile(
    r"^(?:\[\d+\]\s*)?(?:a |the )?load factor (?:describes|indicates|measures) how full (?:the |a )?(?:hash )?table is$"
)


def source_claim_issue(claim, evidence):
    """A recognised fullness-only definition cannot establish a causal effect.

    Other wording, explicit causal support elsewhere in the cited passages, and
    ordinary paraphrases still go to the semantic verifier. False absence or
    document coverage is never inferred from this check.
    """
    claim = plain(claim)
    if not ("load factor" in claim and EFFECT.search(claim) and OUTCOME.search(claim)):
        return None
    pieces = sentences(evidence)
    definitions = [s for s in pieces if "load factor" in s]
    if not definitions or not all(DEFINITION.fullmatch(s) for s in definitions):
        return None
    if any(EFFECT.search(s) and OUTCOME.search(s) for s in pieces):
        return None
    return (
        "The cited material defines load factor as table fullness but does not establish "
        "the added causal claim about collisions or performance. Keep the supported "
        "definition separate; omit the extra claim from the sourced section."
    )


def background_issues(text):
    """Reject recognised universal tombstone requirements, preserving qualifiers.

    Negations, corrections and explicit implementation scoping are deliberately
    left to the reviewer. This is not a general natural-language entailment test.
    """
    for sentence in sentences(text):
        if "open addressing" not in sentence:
            continue
        match = re.search(
            r"\b(?:requires?|needs?|must use)\s+(?:\w+\s+){0,4}tombstones?\b", sentence
        )
        if not match:
            continue
        context = sentence[: match.start()]
        if re.search(
            r"\b(?:not|never|doesn't|do not|incorrect|wrong|false|myth)\b", context
        ):
            continue
        if re.search(
            r"\b(?:some|certain|many|most|often|usually|typically|sometimes|may|might|can)\b",
            context,
        ):
            continue
        if re.search(
            r"\b(?:this|that|our|a specific|the supplied) (?:implementation|algorithm|variant|example)\b|\blazy deletion\b",
            sentence,
        ):
            continue
        return [
            "Do not say open addressing universally requires tombstones. Tombstones are "
            "one deletion strategy; for linear probing, reinserting the rest of the cluster "
            "is another. Qualify the implementation or omit the deletion claim, and do not "
            "claim every alternative works with every probing scheme."
        ]
    return []
