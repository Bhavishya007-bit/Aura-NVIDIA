"""Package only an explicit committed revision, never the current working files."""

import argparse
import ast
import hashlib
import io
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import zipfile

ROOT_FILES = {
    "Dockerfile",
    ".dockerignore",
    ".gitignore",
    "LICENSE",
    "README.md",
    "JUDGE_QUICKSTART.md",
    "HACKATHON_UPGRADES.md",
    "CHANGELOG.md",
    "auth-migration.sql",
    "compose.yaml",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "index.html",
    "vite.config.ts",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
}
SOURCE_DIRS = {
    "backend",
    "database",
    "src",
    "scripts",
    "sandbox",
    "judge",
    "deploy",
    "docs",
    "evaluation",
    "tests",
}
PRIVATE_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    "uploads",
    ".local_storage",
    "private-data",
    "results",
    "reports",
    "aura-update-backups",
}


def allowed(name):
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or PRIVATE_PARTS.intersection(path.parts)
    ):
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if path.suffix.lower() in {".pem", ".key", ".log", ".zip", ".pyc", ".sqlitedb"}:
        return False
    return name in ROOT_FILES or path.parts[0] in SOURCE_DIRS


def package(root, output, ref):
    sha = subprocess.check_output(
        ["git", "rev-parse", "--verify", ref + "^{commit}"], cwd=root, text=True
    ).strip()
    archive = subprocess.check_output(["git", "archive", "--format=tar", sha], cwd=root)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        for item in source.getmembers():
            if item.isfile() and allowed(item.name):
                files[item.name] = source.extractfile(item).read()
    required = {
        "JUDGE_QUICKSTART.md",
        "LICENSE",
        "Dockerfile",
        "judge/compose.yaml",
        "judge/start.ps1",
        "judge/start.sh",
        "scripts/configure_judge.py",
    }
    if not required.issubset(files):
        raise ValueError(
            "The selected commit does not contain the complete judge build."
        )
    # Read only the authored constant, without importing app/database modules.
    tree = ast.parse(files["backend/production/demo.py"])
    sections = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "SECTIONS" for t in n.targets)
    )
    files["SAMPLE_STUDY_NOTES.md"] = (
        "# Aura synthetic demo notes\n\n"
        + "\n\n".join(f"## {title}\n\n{text}" for title, text in sections)
    ).encode()
    files["BUILD_INFO.txt"] = (
        f"Aura judge test build\nSource commit: {sha}\n"
        "No provider credentials, student uploads or live evaluation reports are included.\n"
        "Start with JUDGE_QUICKSTART.md.\n"
    ).encode()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    target = output / "Aura-Judge-Build.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(
                "Aura-Judge-Build/" + name, date_time=(2026, 1, 1, 0, 0, 0)
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
            bundle.writestr(info, data)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(
        f"{digest}  {target.name}\n", encoding="utf-8"
    )
    print(f"Packaged {len(files)} files from committed revision {sha}.")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ref",
        required=True,
        help="Reviewed commit SHA; working tree edits are excluded.",
    )
    parser.add_argument("--output", default="outputs/judge-release")
    args = parser.parse_args()
    package(Path(__file__).resolve().parents[1], args.output, args.ref)
