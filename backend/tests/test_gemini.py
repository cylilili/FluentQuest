import unittest
from unittest.mock import patch

import httpx2
from google import genai

from app.llm import GeminiProvider, ProviderUnavailable


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
