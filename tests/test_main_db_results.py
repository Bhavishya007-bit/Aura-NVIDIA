"""Regression tests for None database rows; no live database or AI model needed."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fastapi import HTTPException
from psycopg2.extras import Json
from pgvector import Vector

ROOT = Path(__file__).resolve().parents[1]


class DatabaseResultTests(unittest.TestCase):
    def function(self, name, rows):
        tree = ast.parse((ROOT / "backend/main.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        function.decorator_list = []
        connection = Mock()
        cursor = connection.cursor.return_value
        cursor.fetchone.side_effect = rows
        namespace = {"get_connection": lambda: connection, "HTTPException": HTTPException, "Json": Json, "Vector": Vector}
        for annotation in ["StudentRequest", "CourseRequest", "TopicRequest", "ConceptRequest", "SourceRequest", "ChunkEmbeddingRequest", "BatchChunksRequest"]:
            namespace[annotation] = object
        exec(compile(ast.Module(body=[function], type_ignores=[]), "main-db-result-test", "exec"), namespace)
        return namespace[name], connection, cursor

    def request(self):
        return SimpleNamespace(name="Student", email="student@example.com", course_name="Course", course_id=17,
            topic_name="Topic", topic_id=3, concept_name="Concept", concept_id=4, source_name="notes.pdf",
            source_type="pdf", file_path=None, source_id=31, content="A supported source statement.",
            page_number=1, slide_number=None, timestamp_seconds=None, timestamp_end=None, metadata=None, embedding=None)

    def test_missing_insert_rows_roll_back_and_release_connections(self):
        for name in ["create_student", "create_course", "create_topic", "create_concept", "create_source", "store_chunk"]:
            with self.subTest(function=name):
                function, connection, cursor = self.function(name, [None])
                with self.assertRaises(HTTPException) as error:
                    function(self.request())
                self.assertEqual(error.exception.status_code, 500)
                connection.commit.assert_not_called()
                connection.rollback.assert_called_once()
                cursor.close.assert_called_once()
                connection.close.assert_called_once()

    def test_successful_insert_keeps_returned_ids_and_commits(self):
        cases = [("create_student", (7,"Student","student@example.com"), "student_id",7),
            ("create_course",(17,"Course"),"course_id",17), ("create_topic",(3,17,"Topic"),"topic_id",3),
            ("create_concept",(4,3,"Concept"),"concept_id",4),
            ("create_source",(31,17,"notes.pdf","pdf",None,"uploaded"),"source_id",31),
            ("store_chunk",(99,),"chunk_id",99)]
        for name, row, key, identifier in cases:
            with self.subTest(function=name):
                function, connection, cursor = self.function(name, [row])
                self.assertEqual(function(self.request())[key],identifier)
                connection.commit.assert_called_once()
                connection.rollback.assert_not_called()
                cursor.close.assert_called_once()
                connection.close.assert_called_once()

    def test_batch_failure_rolls_back_earlier_insert(self):
        function, connection, cursor = self.function("create_chunks_batch", [(99,),None])
        with self.assertRaises(HTTPException):
            function(SimpleNamespace(chunks=[self.request(),self.request()]))
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()
        cursor.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
