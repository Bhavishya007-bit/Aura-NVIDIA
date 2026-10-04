import os
import time

from openai import OpenAI
from openai import RateLimitError


MODEL_NAME = "qwen/qwen3.8-27b:free"


class LLM:

    def __init__(self):

        api_key = os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable is not set."
            )

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )

    def generate(
        self,
        prompt: str,
        max_retries: int = 3
    ) -> str:

        for attempt in range(max_retries):

            try:

                response = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )

                content = response.choices[0].message.content

                if content:
                    return content.strip()

                raise RuntimeError(
                    "LLM returned an empty response."
                )

            except RateLimitError:

                if attempt == max_retries - 1:

                    raise RuntimeError(
                        "LLM rate limit exceeded after "
                        f"{max_retries} attempts."
                    )

                wait_time = 5 * (attempt + 1)

                print(
                    f"\nLLM rate limited. "
                    f"Retrying in {wait_time} seconds..."
                )

                time.sleep(wait_time)

        raise RuntimeError("LLM generation failed.")