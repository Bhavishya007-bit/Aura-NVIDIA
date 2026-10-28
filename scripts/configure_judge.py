"""Create local judge credentials inside the setup container, never in the image."""

import argparse
import getpass
import os
from pathlib import Path
import re
import secrets
import sys
import warnings

MODEL = "nvidia/Nemotron-3-Ultra-550b-a55b"


def create(directory, key, vision=False):
    target = Path(directory) / ".env.judge"
    if target.exists():
        raise ValueError("Judge settings already exist. They were not overwritten.")
    # Single quoted Compose values prevent interpolation. Keep credentials to
    # printable token characters; never include untrusted text as env syntax.
    if not re.fullmatch(r"[A-Za-z0-9_./:+~=-]{12,4096}", key or ""):
        raise ValueError(
            "Enter the Token Factory API credential, not a URL or account password."
        )
    values = {
        "AURA_JUDGE_DB_PASSWORD": secrets.token_hex(24),
        "AUTH_JWT_SECRET": secrets.token_urlsafe(48),
        "AURA_JUDGE_DEMO_ENABLED": "false",
        "AURA_DEMO_EMAIL": "judge@aura.example.org",
        "AURA_DEMO_PASSWORD": secrets.token_urlsafe(24),
        "NEBIUS_API_KEY": key,
        "NEBIUS_BASE_URL": "https://api.tokenfactory.us-central1.nebius.com/v1",
        "NEBIUS_MODEL": MODEL,
        "NEBIUS_COVERAGE_MODEL": MODEL,
        "NEBIUS_ANSWER_MODEL": MODEL,
        "NEBIUS_DEEP_MODEL": MODEL,
        "NEBIUS_MAX_TOKENS": "16384",
        "NEBIUS_JSON_MAX_TOKENS": "16384",
        "NEBIUS_READ_TIMEOUT": "180",
        "AURA_MAX_ANSWER_TOKENS": "32768",
        "NEBIUS_SUMMARY_REASONING_EFFORT": "none",
        "NEBIUS_VERIFICATION_REASONING_EFFORT": "none",
        "AURA_SUMMARY_BACKGROUND": "true",
        "AURA_USER_DAILY_TOKENS": "500000",
        "AURA_GLOBAL_DAILY_TOKENS": "2000000",
        "STUDY_DAILY_TOKEN_BUDGET": "1000000",
        "AURA_JUDGE_VISION_MODEL": "gemma3:4b" if vision else "",
    }
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            "# Private local judge settings. Never upload or share this file.\n"
        )
        stream.writelines(f"{name}='{value}'\n" for name, value in values.items())
    return target


def show_login(directory):
    # Only expose the local demo login. Never dump the env file/provider key.
    data = {}
    for line in (
        (Path(directory) / ".env.judge").read_text(encoding="utf-8").splitlines()
    ):
        name, sep, value = line.partition("=")
        if sep and name in {"AURA_DEMO_EMAIL", "AURA_DEMO_PASSWORD", "AURA_JUDGE_DEMO_ENABLED"}:
            data[name] = value.strip().strip("'")
    print("Open http://localhost:8888")
    demo = os.getenv("AURA_DEMO_ENABLED", os.getenv("AURA_JUDGE_DEMO_ENABLED", data.get("AURA_JUDGE_DEMO_ENABLED", "false"))).strip().lower() in ("true", "1", "yes", "on")
    if not demo:
        print("Create your own Aura account at http://localhost:8888/signup, then upload your material.")
        print("Choose a new Aura password, not your email-account password. No shared judge login is required.")
        return
    print("Demo email:", data.get("AURA_DEMO_EMAIL", "Not configured"))
    print("Local demo password:", data.get("AURA_DEMO_PASSWORD", "Not configured"))
    print(
        "Wait for Aura Demo Study Notes.pdf to finish preparing before asking about it."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="/config")
    parser.add_argument("--vision", action="store_true")
    parser.add_argument("--show-login", action="store_true")
    args = parser.parse_args()
    try:
        if args.show_login:
            show_login(args.directory)
        elif (Path(args.directory) / ".env.judge").exists():
            print("Existing judge settings preserved.")
        else:
            if not sys.stdin.isatty():
                raise ValueError(
                    "Run setup in an interactive terminal so the key can be entered without echo."
                )
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                try:
                    key = getpass.getpass("Private judge Token Factory key (hidden): ")
                except getpass.GetPassWarning:
                    raise ValueError(
                        "This terminal cannot hide input. Use a regular interactive terminal."
                    ) from None
            create(args.directory, key.strip(), args.vision)
            print("Private judge settings created. No provider credential was printed.")
    except (ValueError, OSError) as error:
        # Never include input or exception details that might contain a key.
        if isinstance(error, ValueError):
            raise SystemExit(str(error)) from None
        raise SystemExit(
            "Could not read or save judge settings. Check folder permissions."
        ) from None


if __name__ == "__main__":
    main()
