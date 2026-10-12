"""Create laptop-specific configuration without overwriting existing settings."""
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def write_new(path: Path, content: str) -> bool:
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(content)
        path.chmod(0o600)
        print(f"Created {path.relative_to(ROOT)}.")
        return True
    except FileExistsError:
        print(f"Kept existing {path.relative_to(ROOT)}.")
        return False


def main() -> None:
    template = (ROOT / "backend/.env.example").read_text(encoding="utf-8")
    template = template.replace("replace_with_your_local_database_password", secrets.token_urlsafe(24))
    template = template.replace("replace_with_a_random_secret", secrets.token_urlsafe(48))
    write_new(ROOT / "backend/.env", template)
    write_new(ROOT / ".env.local", (ROOT / ".env.example").read_text(encoding="utf-8"))
    print("For native PostgreSQL, edit backend/.env to match your existing database and port.")


if __name__ == "__main__":
    main()
