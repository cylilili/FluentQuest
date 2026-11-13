import logging
import os
from dataclasses import dataclass
from typing import Protocol

from google import genai
from google.genai import errors, types
from httpx2 import RequestError, TimeoutException

logger = logging.getLogger(__name__)


class ProviderUnavailable(Exception):
    pass


class ProviderTimeout(Exception):
    pass


class ProviderResponseError(Exception):
    pass


@dataclass(frozen=True)
class ToolCall:
    name: str | None
    arguments: dict


class LLMProvider(Protocol):
    def generate_json(self, *, instructions: str, content: str, schema: dict) -> str: ...

    def request_tool_call(
        self, *, instructions: str, content: str, tool_name: str,
        tool_description: str, tool_parameters: dict
    ) -> ToolCall | None: ...


class GeminiProvider:
    def generate_json(self, *, instructions: str, content: str, schema: dict) -> str:
        response = self._generate_content(
            content,
            types.GenerateContentConfig(
                system_instruction=instructions,
                response_mime_type="application/json",
                response_json_schema=schema,
                max_output_tokens=4096,
            ),
            types.HttpOptions(
                timeout=25_000,
                retry_options=types.HttpRetryOptions(
                    attempts=2,
                    initial_delay=1.0,
                    max_delay=2.0,
                    http_status_codes=[503],
                ),
            ),
        )
        if not response.text:
            raise ProviderResponseError("Gemini returned no questions.")
        return response.text

    def request_tool_call(
        self, *, instructions: str, content: str, tool_name: str,
        tool_description: str, tool_parameters: dict
    ) -> ToolCall | None:
        response = self._generate_content(
            content,
            types.GenerateContentConfig(
                system_instruction=instructions,
                tools=[types.Tool(function_declarations=[
                    types.FunctionDeclaration(
                        name=tool_name, description=tool_description, parameters=tool_parameters,
                    )
                ])],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                max_output_tokens=512,
            ),
            types.HttpOptions(
                # The SDK sends this as X-Server-Timeout. Gemini requires at least 10 seconds.
                timeout=12_000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        calls = response.function_calls or []
        if len(calls) > 1:
            raise ProviderResponseError("Gemini returned multiple tool calls.")
        if not calls:
            finish_reason = response.candidates[0].finish_reason if response.candidates else None
            logger.warning("Gemini returned no tutor tool call (finish reason: %s)", finish_reason)
            return None
        return ToolCall(name=calls[0].name, arguments=calls[0].args or {})

    def _generate_content(
        self, content: str, config: types.GenerateContentConfig, http_options: types.HttpOptions
    ) -> types.GenerateContentResponse:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ProviderUnavailable("Set GEMINI_API_KEY on the backend to generate a quest.")

        model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        try:
            with genai.Client(
                api_key=api_key,
                vertexai=False,
                http_options=http_options,
            ) as client:
                return client.models.generate_content(model=model, contents=content, config=config)
        except TimeoutException:
            raise ProviderTimeout("Gemini timed out. Try again.") from None
        except RequestError:
            raise ProviderUnavailable("Could not connect to Gemini. Try again.") from None
        except errors.APIError as exc:
            if config.tools:
                # Tutor requests contain only the skill and attempt metadata.
                detail = (exc.message or "No error detail returned").replace(api_key, "[redacted]")
                logger.warning(
                    "Gemini tutor request failed with status %s (%s): %s",
                    exc.code,
                    exc.status or "unknown",
                    " ".join(detail.split())[:500],
                )
            else:
                logger.warning("Gemini generation failed with status %s", exc.code)
            if exc.code in (401, 403):
                raise ProviderUnavailable("Check the backend Gemini API key and permissions.") from None
            if exc.code == 404:
                raise ProviderUnavailable("The configured Gemini model is unavailable.") from None
            if exc.code == 429:
                raise ProviderUnavailable("Gemini quota is unavailable. Try again later.") from None
            if exc.code == 503:
                raise ProviderUnavailable("Gemini is temporarily unavailable. Try again in a moment.") from None
            raise ProviderUnavailable("Gemini could not generate questions. Try again.") from None


def get_llm_provider() -> LLMProvider:
    return GeminiProvider()
