"""Offline checks for judge setup and committed-source packaging."""

import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from scripts.configure_judge import create, show_login
from scripts.package_judge import allowed, package


class JudgePackageTests(unittest.TestCase):
    def test_config_is_private_and_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            target = create(folder, "synthetic-token-for-offline-test", True)
            first = target.read_text()
            self.assertIn("AURA_JUDGE_VISION_MODEL='gemma3:4b'", first)
            self.assertIn("AURA_JUDGE_DEMO_ENABLED='false'", first)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                create(folder, "replacement-test-token")
            self.assertEqual(first, target.read_text())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                show_login(folder)
            self.assertIn("/signup", out.getvalue())
            self.assertNotIn("judge@aura.example.org", out.getvalue())
            self.assertNotIn("synthetic-token", out.getvalue())
            self.assertNotIn("AUTH_JWT_SECRET", out.getvalue())

    def test_env_injection_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for key in [
                "short",
                "token\nAURA_ENV=local",
                "token'quoted-value",
                "token${HOME}value",
                "https://token with spaces",
            ]:
                with self.assertRaises(ValueError):
                    create(folder, key)
                self.assertFalse((Path(folder) / ".env.judge").exists())

    def test_private_paths_are_excluded_even_if_committed(self):
        for name in [
            "backend/.env",
            "judge/.env.judge",
            "backend/uploads/slides.pdf",
            "evaluation/results/judge_calibration.json",
            "evaluation/reports/live.json",
            "backend/.local_storage/data",
            "deploy/secret.key",
            "src/../../private-data/file",
        ]:
            self.assertFalse(allowed(name), name)
        for name in [
            "judge/start.ps1",
            "src/App.tsx",
            "backend/.env.example",
            "LICENSE",
        ]:
            self.assertTrue(allowed(name), name)

    def test_package_uses_commit_and_ignores_dirty_files(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as out:
            root = Path(folder)

            def git(*args):
                return subprocess.check_output(
                    ["git", *args], cwd=root, stderr=subprocess.DEVNULL
                )

            git("init")
            git("config", "user.name", "Offline test")
            git("config", "user.email", "test@example.invalid")
            entries = [
                "JUDGE_QUICKSTART.md",
                "LICENSE",
                "Dockerfile",
                "judge/compose.yaml",
                "judge/start.ps1",
                "judge/start.sh",
                "scripts/configure_judge.py",
                "backend/production/demo.py",
                "judge/.env.judge",
            ]
            for name in entries:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "SECTIONS = [('Original topic', 'Authored synthetic content')]"
                    if name.endswith("demo.py")
                    else "committed"
                )
            git("add", ".")
            git("commit", "-qm", "Authored offline fixture")
            (root / "LICENSE").write_text("dirty-do-not-package")
            with contextlib.redirect_stdout(io.StringIO()):
                target = package(root, out, "HEAD")
            with zipfile.ZipFile(target) as bundle:
                names = bundle.namelist()
                self.assertNotIn("Aura-Judge-Build/judge/.env.judge", names)
                self.assertEqual(bundle.read("Aura-Judge-Build/LICENSE"), b"committed")
                self.assertIn(
                    b"Original topic",
                    bundle.read("Aura-Judge-Build/SAMPLE_STUDY_NOTES.md"),
                )
                self.assertEqual(
                    bundle.getinfo("Aura-Judge-Build/judge/start.sh").external_attr
                    >> 16
                    & 0o777,
                    0o755,
                )
            self.assertTrue((Path(out) / "SHA256SUMS.txt").exists())

    def test_compose_has_no_host_docker_socket_or_public_database(self):
        # The actual compose configuration is also resolved and booted in CI.
        text = (Path(__file__).resolve().parents[1] / "judge/compose.yaml").read_text()
        self.assertIn("127.0.0.1:8888:8000", text)
        self.assertNotIn("/var/run/docker.sock", text)
        self.assertNotIn("5432:5432", text)
        self.assertIn("AURA_CODE_BACKEND: disabled", text)


if __name__ == "__main__":
    unittest.main()
