import json
import unittest
from unittest.mock import patch

import httpx2
from google import genai
from google.genai.errors import ClientError

from app.llm import GeminiProvider, ProviderUnavailable, ToolCall


HINT_PARAMETERS = {
    "type": "OBJECT",
    "properties": {"skill": {"type": "STRING", "enum": ["Main Idea"]}},
    "required": ["skill"],
}


class GeminiRetryTests(unittest.TestCase):
    def generate(self, statuses):
        responses = iter(statuses)

        def respond(request):
            status = next(responses)
            if status == 200:
                return httpx2.Response(200, json={
                    "candidates": [{
                        "content": {"role": "model", "parts": [{"text": "{}"}]},
                        "finishReason": "STOP",
                    }],
                })
            return httpx2.Response(status, json={"error": {"code": status, "message": "Test failure"}})

        client_class = genai.Client

        def build_client(**kwargs):
            kwargs["http_options"].client_args = {"transport": httpx2.MockTransport(respond)}
            return client_class(**kwargs)

        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test-only", "GOOGLE_GENAI_HTTP_CLIENT": "httpx2"}),
            patch.object(genai, "Client", side_effect=build_client),
            patch("tenacity.nap.time.sleep"),
        ):
            try:
                return GeminiProvider().generate_json(
                    instructions="Test instructions", content="Test passage", schema={"type": "object"},
                )
            finally:
                self.assertIsNone(next(responses, None))

    def test_503_retries_and_returns_success(self):
        self.assertEqual(self.generate([503, 200]), "{}")

    def test_503_stops_after_second_failure(self):
        with self.assertRaisesRegex(ProviderUnavailable, "temporarily unavailable"):
            self.generate([503, 503])

    def test_permission_error_is_not_retried(self):
        with self.assertRaisesRegex(ProviderUnavailable, "API key and permissions"):
            self.generate([403])

    def test_tutor_request_error_logs_gemini_details_without_the_api_key(self):
        api_key = "test-only-key"
        error = ClientError(400, {
            "error": {"status": "INVALID_ARGUMENT", "message": f"Invalid request for {api_key}."},
        })
        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": api_key}),
            patch.object(genai, "Client", side_effect=error),
            self.assertLogs("app.llm", level="WARNING") as logs,
            self.assertRaises(ProviderUnavailable),
        ):
            GeminiProvider().request_tool_call(
                instructions="Help the learner retry.", content="Main Idea",
                tool_name="give_hint", tool_description="Give a reading hint.",
                tool_parameters=HINT_PARAMETERS,
            )

        self.assertIn("400 (INVALID_ARGUMENT): Invalid request for [redacted].", logs.output[0])
        self.assertNotIn(api_key, logs.output[0])

    def test_sdk_sends_function_declaration_and_parses_tool_call(self):
        requests = []

        def respond(request):
            self.assertGreaterEqual(int(request.headers["X-Server-Timeout"]), 10)
            requests.append(json.loads(request.content))
            return httpx2.Response(200, json={
                "candidates": [{
                    "content": {"role": "model", "parts": [{
                        "functionCall": {"name": "give_hint", "args": {"skill": "Main Idea"}},
                    }]},
                    "finishReason": "STOP",
                }],
            })

        client_class = genai.Client

        def build_client(**kwargs):
            kwargs["http_options"].client_args = {"transport": httpx2.MockTransport(respond)}
            return client_class(**kwargs)

        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test-only", "GOOGLE_GENAI_HTTP_CLIENT": "httpx2"}),
            patch.object(genai, "Client", side_effect=build_client),
        ):
            call = GeminiProvider().request_tool_call(
                instructions="Help the learner retry.", content="Main Idea",
                tool_name="give_hint", tool_description="Give a reading hint.",
                tool_parameters=HINT_PARAMETERS,
            )

        self.assertEqual(call, ToolCall("give_hint", {"skill": "Main Idea"}))
        self.assertEqual(len(requests), 1)
        declaration = requests[0]["tools"][0]["functionDeclarations"][0]
        self.assertEqual(declaration["name"], "give_hint")
        self.assertEqual(declaration["parameters"], HINT_PARAMETERS)
