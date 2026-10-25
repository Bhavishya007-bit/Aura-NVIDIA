"""Measured batch summaries. No observations means unmeasured, never perfect."""


def summarize(records):
    rows = [r.get("metrics", r) for r in records]
    raw = sum(r.get("raw", 0) for r in rows)
    valid = sum(r.get("valid", 0) for r in rows)
    cited = sum(r.get("cited", 0) for r in rows)
    supported = sum(r.get("supported", r.get("cited", 0)) for r in rows)
    duplicates = sum(r.get("duplicates", 0) for r in rows)

    def adherence(expected_key, actual_key):
        values = []
        for r in rows:
            expected = r.get(expected_key, {})
            actual = r.get(actual_key, {})
            if not sum(expected.values()) or not sum(actual.values()):
                continue
            values.append(
                max(
                    0,
                    1
                    - sum(
                        abs(
                            actual.get(k, 0) / sum(actual.values())
                            - expected.get(k, 0) / sum(expected.values())
                        )
                        for k in set(expected) | set(actual)
                    )
                    / 2,
                )
            )
        return sum(values) / len(values) if values else None

    return {
        "batches": len(rows),
        "schema_valid_rate": valid / raw if raw else None,
        "citation_validity_rate": cited / valid if valid else None,
        "duplicate_rate": duplicates / supported if supported else None,
        "type_mix_adherence": adherence("expected_type_mix", "type_mix"),
        "difficulty_mix_adherence": adherence(
            "expected_difficulty_mix", "difficulty_mix"
        ),
        "mean_batch_latency_s": (
            sum(r.get("latency", 0) for r in rows) / len(rows) if rows else None
        ),
        "prompt_tokens": sum(r.get("prompt_tokens", 0) for r in rows) if rows else None,
        "cached_tokens": sum(r.get("cached_tokens", 0) for r in rows) if rows else None,
        "completion_tokens": (
            sum(r.get("completion_tokens", 0) for r in rows) if rows else None
        ),
        "usage_complete": bool(rows)
        and all(r.get("usage_complete", False) for r in rows),
        "notice": "Only recorded, provider-reported measurements are included. Missing usage on cancelled streams is not a measured zero.",
    }
