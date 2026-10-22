"""Run an opt-in, paid coverage benchmark over fixed synthetic evidence."""
import argparse
import json
from pathlib import Path
import statistics
import time

from backend.ai.answer_contract import CoverageDecision
from backend.ai.source_aware import prompt

LABELS = ("fully_covered", "partially_covered", "not_covered")


def metrics(records):
    matrix = {gold: {pred: 0 for pred in (*LABELS, "unknown")} for gold in LABELS}
    for row in records:
        matrix[row["expected"]][row.get("predicted", "unknown")] += 1
    covered = [r for r in records if r["expected"] != "not_covered"]
    false_absence = sum(r.get("predicted") == "not_covered" for r in covered)
    return {"confusion_matrix": matrix, "cases": len(records),
            "accuracy": sum(r.get("predicted") == r["expected"] for r in records) / len(records) if records else None,
            "covered_case_count": len(covered), "false_absence_count": false_absence,
            "false_absence_rate": false_absence / len(covered) if covered else None,
            "unknown_or_failed_count": sum(r.get("predicted", "unknown") == "unknown" for r in records),
            "mean_latency_seconds": statistics.mean(r["latency_seconds"] for r in records) if records else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly allow paid Nebius requests.")
    parser.add_argument("--models", nargs="+", required=True, help="Exact model IDs, copied from your catalog.")
    parser.add_argument("--split", choices=["development", "holdout"], default="development")
    parser.add_argument("--output", default="evaluation/results/coverage_live.json")
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to permit paid API calls. Offline checks: python -m unittest evaluation.check_phase2")
    from backend.ai.llm import LLM
    fixture = json.loads(Path(__file__).with_name("coverage_cases.json").read_text())
    cases = [c for c in fixture["cases"] if c["split"] == args.split]
    reports = []
    for model in args.models:
        client = LLM()
        client.model_name = model
        client.task = "coverage"
        records = []
        for case in cases:
            start = time.perf_counter()
            row = {"id": case["id"], "expected": case["expected"], "predicted": "unknown"}
            try:
                decision = CoverageDecision.model_validate(client.generate_json(
                    json.dumps({"passages": fixture["passages"], "question": case["question"]}),
                    max_retries=1, system_prompt=prompt("coverage_judge.txt"),
                )).check_citations(len(fixture["passages"]))
                row.update(predicted=decision.status, decision=decision.model_dump())
            except Exception as error:
                row["error_type"] = type(error).__name__
            row["latency_seconds"] = time.perf_counter() - start
            records.append(row)
        reports.append({"model": model, "split": args.split, "metrics": metrics(records), "records": records})
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"mode": "live_synthetic_coverage_benchmark", "reports": reports,
        "limitations": "Coverage classification only: not full RAG retrieval, answer quality, or a routing recommendation. Small-sample rates need counts and human review."}, indent=2))
    print(json.dumps([{k: v for k, v in r.items() if k != "records"} for r in reports], indent=2))


if __name__ == "__main__":
    main()
