import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)


class ProviderUnavailable(Exception):
    pass


class ProviderTimeout(Exception):
    pass


class ProviderResponseError(Exception):
    pass


class LLMProvider(Protocol):
    def generate_json(self, *, instructions: str, content: str, schema: dict) -> str: ...


class GeminiProvider:
    def generate_json(self, *, instructions: str, content: str, schema: dict) -> str:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ProviderUnavailable("Set GEMINI_API_KEY on the backend to generate a quest.")

        from google import genai
        from google.genai import errors, types
        from httpx2 import RequestError, TimeoutException

        model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        try:
            with genai.Client(
                api_key=api_key,
                vertexai=False,
                http_options=types.HttpOptions(
                    timeout=45_000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ) as client:
                response = client.models.generate_content(
                    model=model,
                    contents=content,
                    config=types.GenerateContentConfig(
                        system_instruction=instructions,
                        response_mime_type="application/json",
                        response_json_schema=schema,
                        max_output_tokens=4096,
                    ),
                )
        except TimeoutException:
            raise ProviderTimeout("Gemini timed out. Try again.") from None
        except RequestError:
            raise ProviderUnavailable("Could not connect to Gemini. Try again.") from None
        except errors.APIError as exc:
            logger.warning("Gemini generation failed with status %s", exc.code)
            if exc.code in (401, 403):
                raise ProviderUnavailable("Check the backend Gemini API key and permissions.") from None
            if exc.code == 404:
                raise ProviderUnavailable("The configured Gemini model is unavailable.") from None
            if exc.code == 429:
                raise ProviderUnavailable("Gemini quota is unavailable. Try again later.") from None
            raise ProviderUnavailable("Gemini could not generate questions. Try again.") from None

        if not response.text:
            raise ProviderResponseError("Gemini returned no questions.")
        return response.text


def get_llm_provider() -> LLMProvider:
    return GeminiProvider()
