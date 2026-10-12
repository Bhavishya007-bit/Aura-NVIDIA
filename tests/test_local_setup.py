import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SetupTests(unittest.TestCase):
    def test_existing_database_is_never_modified(self):
        module = load("init_database")
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (True,)
        with self.assertRaises(RuntimeError):
            module.initialize(connection)
        self.assertEqual(cursor.execute.call_count,1)
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once()

    def test_empty_database_setup_is_one_transaction(self):
        module = load("init_database")
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (False,)
        module.initialize(connection)
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()
        self.assertEqual(cursor.execute.call_count, 1 + len(module.SQL_FILES))

    def test_migration_failure_rolls_back_entire_setup(self):
        module = load("init_database")
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (False,)
        cursor.execute.side_effect = [None,None,RuntimeError("simulated migration failure")]
        with self.assertRaises(RuntimeError): module.initialize(connection)
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once()

    def test_local_config_preserves_existing_files(self):
        module = load("create_local_config")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "backend").mkdir()
            (root / "backend/.env.example").write_text("DB_PASSWORD=replace_with_your_local_database_password\nAUTH_JWT_SECRET=replace_with_a_random_secret\n")
            (root / ".env.example").write_text("VITE_API_BASE_URL=/api\n")
            with patch.object(module,"ROOT",root), patch("builtins.print"):
                module.main()
                first = (root / "backend/.env").read_text()
                self.assertNotIn("replace_with", first)
                module.main()
                self.assertEqual((root / "backend/.env").read_text(),first)
                self.assertEqual((root / ".env.local").read_text(),"VITE_API_BASE_URL=/api\n")


if __name__ == "__main__": unittest.main()
