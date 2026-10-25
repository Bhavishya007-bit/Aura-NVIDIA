"""Keep checked tutor evidence and review separately labelled model knowledge."""

import json
import logging

from backend.ai.answer_contract import AnswerSection
from backend.ai.answer_quality import wrong_script
from backend.ai.background_review import review_background
from backend.ai.summary_answer import (
    SummaryDraft,
    checked_points,
    literal_excerpt,
    source_section,
)

log = logging.getLogger(__name__)


def recover_tutor(sources, checks, decision, question, request):
    """Salvage whole approved claims; otherwise quote only cited covered evidence.

    Unlike a document overview, a focused answer must not sample arbitrary text
    from the file when generation fails. Coverage status remains unchanged.
    """
    for check in reversed(checks):
        if (
            check.get("stage") != "grounding"
            or check.get("question_validation", {}).get("valid") is not True
        ):
            continue
        points = checked_points(sources, check, question, request)
        if points:
            text = SummaryDraft.model_validate({"sentences": points}).render(
                len(sources), request
            )
            return source_section(text), {
                "valid": True,
                "stage": "tutor_checked_points",
                "response_mode": "checked_points",
                "answers_full_question": False,
                "grounding_validation": {
                    "valid": True,
                    "results": [
                        {
                            "claim": p["text"],
                            "citations": p["citation_ids"],
                            "supported": True,
                        }
                        for p in points
                    ],
                },
            }
    excerpts, seen = [], set()
    for part in decision.covered_parts:
        for number in part.citation_ids:
            if type(number) is not int or not 1 <= number <= len(sources):
                continue
            text = literal_excerpt(sources[number - 1].get("content", ""), question)
            if not text or text in seen:
                continue
            seen.add(text)
            excerpts.append(f"“{text}” [{number}]")
            if len(excerpts) >= 3:
                break
        if len(excerpts) >= 3:
            break
    if excerpts:
        return source_section("\n\n".join(excerpts)), {
            "valid": True,
            "stage": "tutor_source_excerpts",
            "response_mode": "extractive",
            "answers_full_question": False,
            "proof": "Each quotation is an exact substring of a passage cited by a covered part.",
        }
    return None, None


def tutor_background(client, payload, system_prompt, source_text, depth):
    """At most two drafts/reviews; never approve an unchanged rejected draft."""
    payload = dict(payload, checked_source_text=source_text)
    rejected = set()
    for attempt in range(2):
        stage = "generation"
        try:
            text = client.generate(
                json.dumps(payload), max_retries=1, system_prompt=system_prompt
            ).strip()
            stage = "validation"
            section = AnswerSection(
                kind="beyond", text=text, provenance="model_knowledge", verified=False
            )
            if wrong_script(text, payload["question"]):
                raise ValueError("Wrong answer language")
            key = " ".join(text.split())
            if key in rejected:
                break
            stage = "review"
            review = review_background(
                client, payload["question"], source_text, text, depth
            )
            if review.acceptable:
                log.info(
                    "tutor_background=approved attempt=%s verified=False", attempt + 1
                )
                return section
            rejected.add(key)
            payload.update(
                prior_draft=text,
                feedback={
                    "corrections": review.issues,
                    "instruction": "Correct or remove each flagged claim. Preserve the question and source boundaries; label invented teaching examples as hypothetical. Return the revised explanation only.",
                },
            )
            log.info(
                "tutor_background=rejected attempt=%s issue_count=%s",
                attempt + 1,
                len(review.issues),
            )
        except Exception as error:
            log.warning(
                "tutor_background=unavailable stage=%s error_type=%s",
                stage,
                type(error).__name__,
            )
            break
    return None
