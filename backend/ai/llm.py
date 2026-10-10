import os
import time

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError


load_dotenv("backend/.env")


MODEL_NAME = "openrouter/free"


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

                print(
                    f"\nLLM returned an empty response "
                    f"(attempt {attempt + 1}/{max_retries})."
                )

            except RateLimitError as error:

                error_message = str(error)

                if "free-models-per-day" in error_message:

                    raise RuntimeError(
                        "OpenRouter daily free-model quota has "
                        "been exhausted. Please wait for the "
                        "daily reset or use another available "
                        "free model."
                    )

                print(
                    f"\nLLM temporarily rate limited "
                    f"(attempt {attempt + 1}/{max_retries})."
                )

            if attempt < max_retries - 1:

                wait_time = 5 * (attempt + 1)

                print(
                    f"Retrying in {wait_time} seconds..."
                )

                time.sleep(wait_time)


        raise RuntimeError(
            f"LLM generation failed after "
            f"{max_retries} attempts."
        )