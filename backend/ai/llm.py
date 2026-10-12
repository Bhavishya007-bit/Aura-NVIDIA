import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv("backend/.env")


class LLM:
    """Local Ollama client; no OpenRouter client or credentials are used."""

    def __init__(self):
        self.model_name = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.base_url = base if base.endswith("/api/chat") else base + "/api/chat"

    def _request(self, prompt: str, max_retries: int, json_mode: bool) -> str:
        attempts = max(1, min(int(max_retries), 3))
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": 0 if json_mode else 0.1,
                "num_predict": 256 if json_mode else 768,
                "num_ctx": 8192,
            },
        }
        if json_mode:
            payload["format"] = "json"

        for attempt in range(attempts):
            try:
                response = requests.post(
                    self.base_url,
                    json=payload,
                    timeout=(5, 300),
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise RuntimeError("Ollama returned an invalid response object.")
                message = data.get("message")
                if not isinstance(message, dict):
                    raise RuntimeError("Ollama returned no assistant message.")
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("Ollama returned an empty response.")
                if data.get("done_reason") == "length":
                    raise RuntimeError(
                        "Ollama reached the output limit before finishing."
                    )
                return content.strip()
            except requests.HTTPError as error:
                status = (
                    error.response.status_code if error.response is not None else None
                )
                if status not in {429, 502, 503, 504} or attempt == attempts - 1:
                    raise RuntimeError(
                        "Local Ollama request failed. Check the backend log and Ollama model."
                    ) from error
            except (requests.ConnectionError, requests.Timeout) as error:
                if attempt == attempts - 1:
                    raise RuntimeError(
                        "Local Ollama could not be reached or timed out."
                    ) from error
            except (requests.RequestException, ValueError) as error:
                raise RuntimeError(
                    "Local Ollama returned an invalid response."
                ) from error
            time.sleep(0.5 * (attempt + 1))
        raise RuntimeError("Local Ollama request failed.")

    def generate(self, prompt: str, max_retries: int = 3) -> str:
        return self._request(prompt, max_retries, json_mode=False)

    def generate_json(self, prompt: str, max_retries: int = 2) -> dict:
        """Use Ollama's JSON mode for a machine-readable verification result."""
        response = self._request(prompt, max_retries, json_mode=True)
        try:
            result = json.loads(response)
        except json.JSONDecodeError as error:
            raise RuntimeError("Ollama returned invalid verification JSON.") from error
        if not isinstance(result, dict):
            raise RuntimeError("Ollama verification JSON must be an object.")
        return result
