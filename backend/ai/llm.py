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


def _token_count(value):
    """Keep provider diagnostics numeric; never log arbitrary response values."""
    return value if type(value) is int and value >= 0 else None


class LLMResponseError(RuntimeError):
    """Safe, structured provider failure metadata for bounded recovery."""

    def __init__(self, code, *, max_tokens, reasoning_tokens=None):
        super().__init__(f"Nebius returned an unusable response. See failure_code={code} in the backend log.")
        self.failure_code = code
        self.max_tokens = max_tokens
        self.reasoning_tokens = reasoning_tokens


class LLMConnectionError(RuntimeError):
    """Transport failure with fixed metadata; no endpoint, prompt or credentials."""

    def __init__(self, *, timed_out=False):
        super().__init__('The model connection timed out.' if timed_out else 'The model could not be reached.')
        self.failure_code = 'model_timeout' if timed_out else 'model_connection_failed'


def generate_verification_json(llm, prompt):
    """One judge call, plus one targeted recovery for a truncated response only."""
    configure = getattr(type(llm), 'for_verification', None)
    client = configure(llm) if callable(configure) else llm
    try:
        return client.generate_json(prompt, max_retries=1)
    except LLMResponseError as error:
        if error.failure_code != 'output_truncated' or not isinstance(client, LLM):
            raise
        # Never parse partial decisions or rejudge valid negative verdicts.
        # Reserve only measured reasoning overhead, within a small judge cap
        # and the operator's existing overall ceiling.
        budget = min(8192, error.max_tokens + (error.reasoning_tokens or 0))
        retry = client.with_output_budget(budget, exact=True)
        logger.warning('verification_retry failure_code=output_truncated max_tokens=%s',
                       retry.json_max_tokens)
        return retry.generate_json(prompt, max_retries=1)


class LLM:
    """Nebius Token Factory client with Aura's existing public interface."""

    def __init__(self):
        self.api_key = os.getenv("NEBIUS_API_KEY", "").strip()
        self.model_name = os.getenv("NEBIUS_MODEL", "").strip()
        self.task = "answer"
        self.reasoning_effort = None
        self.last_usage = None

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

    def with_output_budget(self, tokens: int, *, exact=False):
        """Bound larger generation budgets to this answer, not its small judges."""
        client = copy.copy(self)
        ceiling = max(4096, min(32768, int(os.getenv('AURA_MAX_ANSWER_TOKENS', '16384'))))
        budget = max(1, min(int(tokens), ceiling))
        client.max_tokens = budget if exact else min(ceiling, max(self.max_tokens, budget))
        client.json_max_tokens = budget if exact else min(ceiling, max(self.json_max_tokens, budget))
        return client

    def for_summary(self):
        """Reserve output for long-form writing, without changing judge/deep clients."""
        return self._with_reasoning('NEBIUS_SUMMARY_REASONING_EFFORT')

    def for_verification(self):
        """Keep small structured judges from spending their output on reasoning."""
        client = self._with_reasoning('NEBIUS_VERIFICATION_REASONING_EFFORT')
        client.task = 'verification'
        return client

    def _with_reasoning(self, setting):
        client = copy.copy(self)
        # This default addresses the model/endpoint failure observed in live logs.
        # Other routed models keep provider defaults unless explicitly configured.
        default = ("none" if self.model_name.lower() ==
                   "nvidia/nemotron-3-super-120b-a12b" else "provider")
        effort = os.getenv(setting, "").strip().lower() or default
        if effort not in {"provider", "none", "minimal", "low", "medium", "high", "xhigh"}:
            raise ValueError(f"Invalid {setting}.")
        client.reasoning_effort = None if effort == "provider" else effort
        return client

    def _request(self, prompt: str, max_retries: int, json_mode: bool,
                 system_prompt: str | None = None) -> str:
        # Preserve the old client's meaning: max_retries limits total attempts.
        attempts = max(1, min(int(max_retries), 3))
        from backend.generation_jobs import guard
        guard()
        messages = []

        instructions = system_prompt or ""
        if json_mode:
            instructions += ("\nReturn exactly one valid JSON object matching the "
                             "requested fields. Do not wrap the JSON object in a code fence "
                             "or add commentary outside it. Inside JSON string values, "
                             "use the formatting requested by the task, including Markdown "
                             "when appropriate; escape newlines and quotes correctly.")
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
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(attempts):
            started = time.perf_counter()
            retry_delay = min(2 ** attempt, 8)
            failure_code = "transport"
            finish = None
            input_tokens = output_tokens = reasoning_tokens = None

            from backend.production.limits import reserve,settle
            reservation=reserve(payload);usage={}
            try:
                guard()
                response = requests.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=(10, self.read_timeout),
                    allow_redirects=False,
                )

                if 300 <= response.status_code < 400:
                    failure_code = "unexpected_redirect"
                    raise RuntimeError(
                        "Unexpected redirect. Check NEBIUS_BASE_URL."
                    )

                guard()
                response.raise_for_status()
                failure_code = "response_json"
                data = response.json()

                failure_code = "response_shape"
                if not isinstance(data, dict):
                    raise RuntimeError("Nebius returned an invalid response.")

                usage = data.get("usage")
                if not isinstance(usage, dict):
                    usage = {}
                input_tokens = _token_count(usage.get("prompt_tokens"))
                output_tokens = _token_count(usage.get("completion_tokens"))
                completion_details = usage.get("completion_tokens_details")
                if isinstance(completion_details, dict):
                    reasoning_tokens = _token_count(completion_details.get("reasoning_tokens"))
                self.last_usage = {'prompt_tokens': input_tokens, 'completion_tokens': output_tokens}

                failure_code = "completion_shape"
                choices = data.get("choices")
                if not isinstance(choices, list) or not choices:
                    raise RuntimeError("Nebius returned no completion.")
                choice = choices[0]
                if not isinstance(choice, dict):
                    raise RuntimeError("Nebius returned an invalid completion.")

                finish_reason = choice.get("finish_reason")
                finish = (finish_reason if isinstance(finish_reason, str) and finish_reason in
                          {"stop", "length", "content_filter", "tool_calls", "function_call"} else "other")
                if finish_reason == "length":
                    failure_code = "output_truncated"
                    raise RuntimeError(
                        "Model output was truncated. Review the token limit "
                        "and the selected model's reasoning settings."
                    )
                if finish_reason != "stop":
                    failure_code = "unexpected_finish_reason"
                    raise RuntimeError(
                        "Unexpected completion finish reason."
                    )

                message = choice.get("message")
                content = (
                    message.get("content")
                    if isinstance(message, dict)
                    else None
                )
                if not isinstance(content, str) or not content.strip():
                    failure_code = "empty_content"
                    raise RuntimeError("Nebius returned no answer text.")

                if json_mode:
                    failure_code = "content_json"
                    parsed = json.loads(content)
                    if not isinstance(parsed, dict):
                        failure_code = "content_shape"
                        raise RuntimeError(
                            "Nebius verification JSON must be an object."
                        )

                details = usage.get("prompt_tokens_details")
                cached = details.get("cached_tokens") if isinstance(details, dict) else None
                total_input = usage.get("prompt_tokens")
                if (type(cached) is not int or cached < 0
                    or (type(total_input) is int and cached > total_input)):
                    cached = None

                logger.info(
                    "provider=nebius model=%s json=%s attempt=%s "
                    "latency_s=%.2f prompt_tokens=%s completion_tokens=%s "
                    "task=%s cached_tokens=%s cache_hit=%s status=success "
                    "max_tokens=%s reasoning_tokens=%s reasoning_effort=%s",
                    self.model_name,
                    json_mode,
                    attempt + 1,
                    time.perf_counter() - started,
                    input_tokens,
                    output_tokens,
                    self.task,
                    cached,
                    None if cached is None else int(cached > 0),
                    payload["max_tokens"],
                    reasoning_tokens,
                    self.reasoning_effort or "provider_default",
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
                    raise LLMConnectionError(timed_out=isinstance(error, requests.Timeout)) from error

            except (requests.RequestException, ValueError, RuntimeError) as error:
                logger.warning(
                    "provider=nebius model=%s attempt=%s "
                    "latency_s=%.2f status=invalid_response error_type=%s "
                    "failure_code=%s task=%s json=%s finish_reason=%s "
                    "max_tokens=%s prompt_tokens=%s completion_tokens=%s reasoning_tokens=%s "
                    "reasoning_effort=%s",
                    self.model_name,
                    attempt + 1,
                    time.perf_counter() - started,
                    type(error).__name__,
                    failure_code,
                    self.task,
                    json_mode,
                    finish,
                    payload["max_tokens"],
                    input_tokens,
                    output_tokens,
                    reasoning_tokens,
                    self.reasoning_effort or "provider_default",
                )
                raise LLMResponseError(
                    failure_code, max_tokens=payload["max_tokens"], reasoning_tokens=reasoning_tokens,
                ) from error

            finally:
                settle(reservation,usage)

            time.sleep(retry_delay)

        raise RuntimeError("Nebius request failed.")

    def generate(self, prompt: str, max_retries: int = 3, *, system_prompt: str | None = None) -> str:
        return self._request(prompt, max_retries, json_mode=False, system_prompt=system_prompt)

    def generate_json(self, prompt: str, max_retries: int = 2, *, system_prompt: str | None = None) -> dict:
        response = self._request(prompt, max_retries, json_mode=True, system_prompt=system_prompt)
        return json.loads(response)
