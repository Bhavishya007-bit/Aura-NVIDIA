"""Controlled provider failures: distinct diagnostics without private response data."""
import copy
import os
import unittest
from unittest.mock import Mock, patch

from backend.ai.llm import LLM
from backend.ai.source_aware import SourceAwareTutor
from backend.ai.rag import RAG
from evaluation.check_phase2 import FakeLLM, Retriever, verdict


class ResponseDiagnostics(unittest.TestCase):
    def client(self):
        with patch.dict(os.environ, {"NEBIUS_API_KEY": "private-key",
                                    "NEBIUS_MODEL": "fixture-model"}, clear=True):
            return LLM().with_output_budget(8192)

    def response(self):
        return {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 20117, "completion_tokens": 8192,
                          "completion_tokens_details": {"reasoning_tokens": 7000}}}

    def failure(self, data, code, **kwargs):
        response = Mock(status_code=200)
        response.json.return_value = data
        if "json_error" in kwargs:
            response.json.side_effect = ValueError("private-provider-response")
        with patch("backend.ai.llm.requests.post", return_value=response) as post, \
             self.assertLogs("backend.ai.llm", "WARNING") as logs:
            with self.assertRaisesRegex(RuntimeError, f"failure_code={code}"):
                self.client().generate_json("private-document", max_retries=1)
        self.assertEqual(post.call_count, 1)
        text = " ".join(logs.output)
        self.assertIn(f"failure_code={code}", text)
        self.assertIn("max_tokens=8192", text)
        for private in ("private-document", "private-key", "private-provider-response"):
            self.assertNotIn(private, text)
        return text

    def test_truncated_output_logs_usage_and_reason(self):
        data = self.response()
        data["choices"][0]["finish_reason"] = "length"
        text = self.failure(data, "output_truncated")
        for field in ("finish_reason=length", "prompt_tokens=20117", "completion_tokens=8192",
                      "reasoning_tokens=7000", "task=answer", "json=True"):
            self.assertIn(field, text)

    def test_empty_content_is_distinct(self):
        data = self.response()
        data["choices"][0]["message"]["content"] = ""
        self.failure(data, "empty_content")

    def test_non_json_content_is_distinct(self):
        data = self.response()
        data["choices"][0]["message"]["content"] = "private-provider-response"
        self.failure(data, "content_json")

    def test_wrong_json_shape_is_distinct(self):
        data = self.response()
        data["choices"][0]["message"]["content"] = "[]"
        self.failure(data, "content_shape")

    def test_malformed_envelopes_and_non_json_response(self):
        for data, code in (([], "response_shape"), ({}, "completion_shape"),
                           ({"choices": [None]}, "completion_shape")):
            with self.subTest(code=code, data=data):
                self.failure(data, code)
        self.failure(None, "response_json", json_error=True)

    def test_untrusted_finish_and_token_values_are_redacted(self):
        data = self.response()
        data["choices"][0]["finish_reason"] = "private-provider-response"
        data["usage"] = {"prompt_tokens": "private-provider-response",
                         "completion_tokens": True,
                         "completion_tokens_details": {"reasoning_tokens": -1}}
        text = self.failure(data, "unexpected_finish_reason")
        self.assertIn("finish_reason=other", text)
        self.assertIn("prompt_tokens=None completion_tokens=None reasoning_tokens=None", text)

    def test_success_remains_accepted(self):
        response = Mock(status_code=200)
        response.json.return_value = self.response()
        with patch("backend.ai.llm.requests.post", return_value=response), \
             self.assertLogs("backend.ai.llm", "INFO") as logs:
            self.assertEqual(self.client().generate_json("private-document"), {"ok": True})
        self.assertIn("status=success max_tokens=8192 reasoning_tokens=7000", logs.output[0])

    def test_coverage_schema_log_redacts_input_and_extra_key(self):
        data = copy.deepcopy(verdict())
        data["covered_parts"][0]["citation_ids"] = ["private-document"]
        data["private-key"] = "private-provider-response"
        tutor = SourceAwareTutor(RAG(Retriever(), FakeLLM(decisions=[data])))
        with self.assertLogs("backend.ai.source_aware", "WARNING") as logs:
            result = tutor._judge("private-document", [{"content": "private-document"}])
        self.assertEqual(result.status, "unknown")
        text = " ".join(logs.output)
        self.assertIn("citation_ids", text)
        self.assertIn("int_type", text)
        self.assertIn("extra_forbidden", text)
        self.assertIn("<field>", text)
        for private in ("private-document", "private-key", "private-provider-response"):
            self.assertNotIn(private, text)


if __name__ == "__main__":
    unittest.main()
