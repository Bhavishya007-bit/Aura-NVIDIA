"""Create an ignored production template with fresh secrets; never print them."""

import os, secrets
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    target = root / "deploy/.env.production"
    if target.exists():
        raise SystemExit(
            "deploy/.env.production already exists; it was not overwritten."
        )
    text = (
        (root / "deploy/production.env.example")
        .read_text()
        .replace("replace_with_at_least_32_random_bytes", secrets.token_urlsafe(48))
        .replace(
            "replace_with_a_random_password_at_least_16_characters",
            secrets.token_urlsafe(24),
        )
    )
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(text)
    print(
        "Created deploy/.env.production with random secrets. Add your database URL, Token Factory key and public hostname in that file. Do not commit it."
    )
