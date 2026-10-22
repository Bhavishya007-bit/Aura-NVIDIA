"""Summarize real per-request cache measurements; missing usage stays unknown."""
import argparse
import json
import re


def summarize(lines):
    rows = []
    for line in lines:
        fields = dict(re.findall(r"([a-z_]+)=([^\s]+)", line))
        if fields.get("provider") != "nebius" or fields.get("status") != "success":
            continue
        rows.append(fields)
    def integer(row, key):
        value = row.get(key, "")
        return int(value) if value.isdigit() else None
    reported = [r for r in rows if integer(r, "cached_tokens") is not None]
    token_reported = [r for r in reported if integer(r, "prompt_tokens") is not None]
    prompt_total = sum(integer(r, "prompt_tokens") for r in token_reported)
    return {"successful_requests": len(rows), "cache_usage_reported": len(reported),
            "cache_usage_unknown": len(rows) - len(reported),
            "request_cache_hit_rate": sum(integer(r, "cached_tokens") > 0 for r in reported) / len(reported) if reported else None,
            "cached_input_token_share": sum(integer(r, "cached_tokens") for r in token_reported) / prompt_total if prompt_total else None,
            "note": "Request hit rate uses only requests reporting cache usage; token share uses matching measured input totals. No savings are inferred."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logfile")
    args = parser.parse_args()
    with open(args.logfile, encoding="utf-8") as log:
        print(json.dumps(summarize(log), indent=2))


if __name__ == "__main__":
    main()
