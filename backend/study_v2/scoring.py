"""Server-owned answer keys. Deterministic scoring, with bounded borderline judging."""

import re
from backend.ai.numerical import grade_numeric
from backend.study_v2.contracts import Question


def normalized(text):
    return " ".join(re.findall(r"\w+", str(text).casefold()))


def score(question, answer, mode="partial", judge=None):
    q = (
        question
        if isinstance(question, Question)
        else Question.model_validate(
            {k: v for k, v in question.items() if k in Question.model_fields}
        )
    )
    if mode not in ("partial", "all_or_nothing"):
        raise ValueError("Unsupported scoring mode.")
    extra = {}
    if q.kind in ("multiple_choice", "multiple_select"):
        selected = answer if isinstance(answer, list) else [answer]
        if (
            any(type(i) is not str for i in selected)
            or len(selected) != len(set(selected))
            or set(selected) - {o.id for o in q.options}
        ):
            raise ValueError("Choose only valid, distinct options.")
        if q.kind == "multiple_choice" and len(selected) != 1:
            raise ValueError("Choose exactly one option.")
        keys = set(q.correct_option_ids)
        chosen = set(selected)
        value = (
            float(chosen == keys)
            if q.kind == "multiple_choice" or mode == "all_or_nothing"
            else max(0, (len(chosen & keys) - len(chosen - keys)) / len(keys))
        )
        expected = q.correct_option_ids
        extra["options"] = [
            {**o.model_dump(), "correct": o.id in keys, "selected": o.id in chosen}
            for o in q.options
        ]
    elif q.kind == "numerical":
        result = grade_numeric(
            {
                "expected": q.value,
                "unit": q.unit,
                "absolute_tolerance": q.tolerance,
                "relative_tolerance": 0,
            },
            str(answer),
        )
        value = float(result["correct"])
        expected = result["expected_answer"]
        extra["numerical_feedback"] = result
    else:
        text = normalized(answer)
        terms = [normalized(k) for k in q.rubric_keywords]
        matches = [
            k for k in terms if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", text)
        ]
        ratio = len(matches) / len(terms)
        # Negation and a long answer need judgement even when all keywords occur.
        negated = bool(re.search(r"\b(?:not|never|no|without|incorrect|false)\b", text))
        if text == normalized(q.model_answer):
            value = 1.0
        elif ratio == 0:
            value = 0.0
        elif (
            ratio == 1
            and not negated
            and len(text.split())
            <= max(15, 3 * len(normalized(q.model_answer).split()))
        ):
            value = 1.0
        elif judge is None:
            raise ValueError("This answer needs a borderline rubric check.")
        else:
            result = judge(
                {
                    "question": q.prompt,
                    "model_answer": q.model_answer,
                    "rubric_keywords": q.rubric_keywords,
                    "student_answer": str(answer),
                }
            )
            if type(result.get("correct")) is not bool:
                raise ValueError("Invalid rubric verdict.")
            value = float(result["correct"])
        expected = q.model_answer
        extra["rubric"] = {"matched": matches, "total": len(terms)}
    return {
        "question_id": q.id,
        "score": round(value, 6),
        "correct": value == 1,
        "expected_answer": expected,
        "explanation": q.explanation,
        **extra,
    }
