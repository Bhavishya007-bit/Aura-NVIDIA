import json
import copy
import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


# Resolve backend/.env independently of the working directory.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)


class LLM:
    """Nebius Token Factory client with Aura's existing public interface."""

    def __init__(self):
        self.api_key = os.getenv("NEBIUS_API_KEY", "").strip()
        self.model_name = os.getenv("NEBIUS_MODEL", "").strip()
        self.task = "answer"

        base = os.getenv(
            "NEBIUS_BASE_URL",
            "https://api.tokenfactory.nebius.com/v1",
        ).strip().rstrip("/")
        self.base_url = f"{base}/chat/completions"

        if not self.api_key:
            raise RuntimeError("Set NEBIUS_API_KEY in backend/.env.")
        if not self.model_name or self.model_name == "replace_with_exact_model_id":
            raise RuntimeError("Set NEBIUS_MODEL to an exact model ID.")

        self.max_tokens = int(os.getenv("NEBIUS_MAX_TOKENS", "4096"))
        self.json_max_tokens = int(
            os.getenv("NEBIUS_JSON_MAX_TOKENS", "4096")
        )
        self.read_timeout = float(
            os.getenv("NEBIUS_READ_TIMEOUT", "120")
        )
        if min(self.max_tokens, self.json_max_tokens, self.read_timeout) <= 0:
            raise RuntimeError("Token limits and timeout must be positive.")

    def for_task(self, task: str):
        """Select an explicitly configured tier; unconfigured roles use the tested model."""
        setting = {"coverage": "NEBIUS_COVERAGE_MODEL", "answer": "NEBIUS_ANSWER_MODEL",
                   "deep": "NEBIUS_DEEP_MODEL"}.get(task)
        if setting is None:
            raise ValueError("Unknown LLM task.")
        client = copy.copy(self)
        client.task = task
        client.model_name = os.getenv(setting, "").strip() or self.model_name
        return client

    def _request(self, prompt: str, max_retries: int, json_mode: bool,
                 system_prompt: str | None = None) -> str:
        # Preserve the old client's meaning: max_retries limits total attempts.
        attempts = max(1, min(int(max_retries), 3))
        messages = []

        instructions = system_prompt or ""
        if json_mode:
            instructions += ("\nReturn exactly one valid JSON object matching the "
                             "requested fields. Do not include Markdown or commentary.")
        if instructions:
            messages.append({"role": "system", "content": instructions.strip()})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "temperature": 0 if json_mode else 0.1,
            "max_tokens": (
                self.json_max_tokens if json_mode else self.max_tokens
            ),
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(attempts):
            started = time.perf_counter()
            retry_delay = min(2 ** attempt, 8)

            try:
                response = requests.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=(10, self.read_timeout),
                    allow_redirects=False,
                )

                if 300 <= response.status_code < 400:
                    raise RuntimeError(
                        "Unexpected redirect. Check NEBIUS_BASE_URL."
                    )

                response.raise_for_status()
                data = response.json()

                if not isinstance(data, dict):
                    raise RuntimeError("Nebius returned an invalid response.")

                choices = data.get("choices")
                if not isinstance(choices, list) or not choices:
                    raise RuntimeError("Nebius returned no completion.")
                choice = choices[0]
                if not isinstance(choice, dict):
                    raise RuntimeError("Nebius returned an invalid completion.")

                finish_reason = choice.get("finish_reason")
                if finish_reason == "length":
                    raise RuntimeError(
                        "Model output was truncated. Review the token limit "
                        "and the selected model's reasoning settings."
                    )
                if finish_reason != "stop":
                    raise RuntimeError(
                        f"Unexpected completion finish reason: {finish_reason!r}"
                    )

                message = choice.get("message")
                content = (
                    message.get("content")
                    if isinstance(message, dict)
                    else None
                )
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("Nebius returned no answer text.")

                if json_mode:
                    parsed = json.loads(content)
                    if not isinstance(parsed, dict):
                        raise RuntimeError(
                            "Nebius verification JSON must be an object."
                        )

                usage = data.get("usage")
                if not isinstance(usage, dict):
                    usage = {}
                details = usage.get("prompt_tokens_details")
                cached = details.get("cached_tokens") if isinstance(details, dict) else None
                total_input = usage.get("prompt_tokens")
                if (type(cached) is not int or cached < 0
                    or (type(total_input) is int and cached > total_input)):
                    cached = None

                logger.info(
                    "provider=nebius model=%s json=%s attempt=%s "
                    "latency_s=%.2f prompt_tokens=%s completion_tokens=%s "
                    "task=%s cached_tokens=%s cache_hit=%s status=success",
                    self.model_name,
                    json_mode,
                    attempt + 1,
                    time.perf_counter() - started,
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                    self.task,
                    cached,
                    None if cached is None else int(cached > 0),
                )
                return content.strip()

            except requests.HTTPError as error:
                status = (
                    error.response.status_code
                    if error.response is not None else None
                )
                logger.warning(
                    "provider=nebius model=%s attempt=%s "
                    "latency_s=%.2f status=http_error http_status=%s",
                    self.model_name,
                    attempt + 1,
                    time.perf_counter() - started,
                    status,
                )

                retryable = status in {408, 429, 500, 502, 503, 504}
                if not retryable or attempt == attempts - 1:
                    raise RuntimeError(
                        f"Nebius request failed with HTTP {status}. "
                        "Check credentials, model access, endpoint and quota."
                    ) from error

                if error.response is not None:
                    retry_after = error.response.headers.get("Retry-After")
                    try:
                        retry_delay = min(
                            max(float(retry_after), retry_delay), 30
                        )
                    except (TypeError, ValueError):
                        pass

            except (requests.ConnectionError, requests.Timeout) as error:
                logger.warning(
                    "provider=nebius model=%s attempt=%s "
                    "latency_s=%.2f status=network_error",
                    self.model_name,
                    attempt + 1,
                    time.perf_counter() - started,
                )
                if attempt == attempts - 1:
                    raise RuntimeError(
                        "Nebius could not be reached or timed out."
                    ) from error

            except (requests.RequestException, ValueError, RuntimeError) as error:
                logger.warning(
                    "provider=nebius model=%s attempt=%s "
                    "latency_s=%.2f status=invalid_response error_type=%s",
                    self.model_name,
                    attempt + 1,
                    time.perf_counter() - started,
                    type(error).__name__,
                )
                raise RuntimeError(
                    "Nebius returned an unusable response. "
                    "Inspect the exception cause in the backend log."
                ) from error

            time.sleep(retry_delay)

        raise RuntimeError("Nebius request failed.")

    def generate(self, prompt: str, max_retries: int = 3, *, system_prompt: str | None = None) -> str:
        return self._request(prompt, max_retries, json_mode=False, system_prompt=system_prompt)

    def generate_json(self, prompt: str, max_retries: int = 2, *, system_prompt: str | None = None) -> dict:
        response = self._request(prompt, max_retries, json_mode=True, system_prompt=system_prompt)
        return json.loads(response)
