import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import httpx2
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import URL

from app import db
from app.llm import ProviderTimeout, ProviderUnavailable, ToolCall, get_llm_provider
from app.main import app
from app.quest import AnswerSubmission, submit_answer

ARTICLE = "\n\n".join(
    " ".join(f"The city opened a new library in district {index}." for index in group)
    for group in (range(1, 13), range(13, 25), range(25, 37))
)


class FakeProvider:
    def __init__(self):
        self.defect = None
        self.puzzle = "The city opened a new _____."
        self.calls = 0
        self.tool_calls = 0

    def request_tool_call(self, *, instructions, content, tool_name, tool_description, tool_parameters):
        self.tool_calls += 1
        return ToolCall(name=tool_name, arguments={"skill": json.loads(content)["skill"]})

    def generate_json(self, *, instructions, content, schema):
        self.calls += 1
        passages = json.loads(content)
        questions = {}
        for index, kind in enumerate(("main_idea", "vocabulary", "sentence_puzzle"), 1):
            questions[kind] = {
                "prompt": self.puzzle if index == 3 else "What did the city open?",
                "options": ["school", "library", "park"],
                "correct_option_id": "B",
                "explanation": "The passage says the city opened a library.",
                "source_quote": passages[f"passage_{index}"].split(".", 1)[0] + ".",
            }
        if self.defect == "wrong passage":
            questions["vocabulary"]["source_quote"] = questions["main_idea"]["source_quote"]
        elif self.defect == "duplicate options":
            questions["vocabulary"]["options"] = ["a school", " A   SCHOOL ", "a park"]
        elif self.defect == "invalid answer ID":
            questions["vocabulary"]["correct_option_id"] = "D"
        return json.dumps(questions)


class GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(directory) / "test.sqlite3"
        engine = create_engine(
            URL.create("sqlite", database=str(path)),
            connect_args={"autocommit": sqlite3.LEGACY_TRANSACTION_CONTROL},
        )
        event.listen(engine, "connect", db.enable_foreign_keys)
        self.addCleanup(engine.dispose)
        self.enterContext(patch.multiple(db, DATABASE_PATH=path, engine=engine))
        self.provider = FakeProvider()
        self.enterContext(patch.dict(app.dependency_overrides, {get_llm_provider: lambda: self.provider}))
        await self.enterAsyncContext(app.router.lifespan_context(app))
        self.client = await self.enterAsyncContext(
            httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test")
        )

    async def test_generated_quest_can_be_played_without_exposing_answer_keys(self):
        response = await self.client.post("/api/articles", json={"text": ARTICLE})
        self.assertEqual(response.status_code, 201)
        session = await self.client.post("/api/sessions", json=response.json())
        self.assertEqual(session.status_code, 201)
        url = f"/api/sessions/{session.json()['session_id']}"
        response = await self.client.get(url)
        self.assertEqual(response.status_code, 200)
        snapshot = response.json()
        stages = snapshot["article"]["stages"]
        self.assertEqual([stage["question"]["title"] for stage in stages], [
            "Main Idea", "Vocabulary in Context", "Sentence Puzzle",
        ])
        combined_passages = " ".join(stage["passage"] for stage in stages)
        self.assertEqual(combined_passages.split(), ARTICLE.split())
        for stage in stages:
            self.assertEqual(set(stage["question"]), {"title", "prompt", "options"})
            result = await self.client.post(f"{url}/answers", json={
                "challenge_id": stage["id"],
                "selected_option_id": "B",
                "request_id": stage["id"],
            })
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.json()["correct"])
        saved = (await self.client.get(url)).json()
        self.assertTrue(saved["session_completed"])
        self.assertEqual(saved["xp"], 30)
        self.assertEqual(saved["answers"][-1]["agent_action"], "COMPLETE")
        self.assertEqual(self.provider.tool_calls, 0)

    async def test_tutor_feedback_is_saved_and_replayed_with_the_answer(self):
        session = (await self.client.post("/api/sessions")).json()
        url = f"/api/sessions/{session['session_id']}"
        submission = {
            "challenge_id": "the-warning",
            "selected_option_id": "A",
            "request_id": "first-attempt",
        }
        first = await self.client.post(f"{url}/answers", json=submission)
        self.assertEqual(first.status_code, 200)
        answer = first.json()
        self.assertEqual(answer["agent_action"], "GIVE_HINT")
        self.assertIn("connects the details", answer["feedback"])
        self.assertEqual(answer["xp"], 0)
        self.assertTrue(answer["retry_allowed"])
        replay = await self.client.post(f"{url}/answers", json=submission)
        self.assertEqual(replay.json(), answer)
        self.assertEqual(self.provider.tool_calls, 1)

        correction = {
            **submission, "selected_option_id": "B", "request_id": "second-attempt",
        }
        second = await self.client.post(f"{url}/answers", json=correction)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["agent_action"], "NEXT_CHALLENGE")
        self.assertEqual(second.json()["xp"], 10)
        replay = await self.client.post(f"{url}/answers", json=correction)
        self.assertEqual(replay.json(), second.json())
        self.assertEqual(self.provider.tool_calls, 1)
        snapshot = (await self.client.get(url)).json()
        self.assertEqual(snapshot["xp"], 10)
        saved = snapshot["answers"]
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0]["agent_action"], "GIVE_HINT")
        self.assertEqual(saved[0]["feedback"], answer["feedback"])

    async def test_repeated_miss_on_final_stage_shows_an_example_and_completes_the_quest(self):
        created = await self.client.post("/api/articles", json={"text": ARTICLE})
        self.assertEqual(created.status_code, 201)
        session = await self.client.post("/api/sessions", json=created.json())
        self.assertEqual(session.status_code, 201)
        url = f"/api/sessions/{session.json()['session_id']}"
        snapshot = (await self.client.get(url)).json()
        stages = snapshot["article"]["stages"]
        for stage in stages[:-1]:
            response = await self.client.post(f"{url}/answers", json={
                "challenge_id": stage["id"], "selected_option_id": "B", "request_id": stage["id"],
            })
            self.assertEqual(response.status_code, 200)

        submission = {"challenge_id": stages[-1]["id"], "selected_option_id": "A"}
        with patch.object(self.provider, "request_tool_call", wraps=self.provider.request_tool_call) as model:
            first = await self.client.post(f"{url}/answers", json={**submission, "request_id": "miss-1"})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["agent_action"], "GIVE_HINT")
            self.assertEqual(model.call_args.kwargs["tool_name"], "give_hint")

            second_submission = {**submission, "selected_option_id": "C", "request_id": "miss-2"}
            second = await self.client.post(f"{url}/answers", json=second_submission)
            self.assertEqual(second.status_code, 200)
            result = second.json()
            self.assertEqual(result["agent_action"], "SIMPLIFY")
            self.assertEqual(model.call_args.kwargs["tool_name"], "show_simpler_example")
            self.assertIn("The passage says the city opened a library.", result["feedback"])
            self.assertIn("Simpler example\n", result["feedback"])
            self.assertIn("‘Took a photo’", result["feedback"])
            self.assertFalse(result["retry_allowed"])
            self.assertTrue(result["challenge_completed"])
            self.assertTrue(result["session_completed"])
            self.assertEqual(result["xp"], 20)

            replay = await self.client.post(f"{url}/answers", json=second_submission)
            self.assertEqual(replay.json(), result)
            third = await self.client.post(f"{url}/answers", json={**submission, "request_id": "miss-3"})
            self.assertEqual(third.status_code, 409)
            self.assertEqual(model.call_count, 2)

        restored = (await self.client.get(url)).json()
        saved = next(answer for answer in restored["answers"] if answer["request_id"] == "miss-2")
        self.assertEqual(saved["feedback"], result["feedback"])
        self.assertEqual(saved["agent_action"], "SIMPLIFY")

    async def test_article_library_lists_saved_articles_and_opens_them_without_a_session(self):
        created = await self.client.post("/api/articles", json={"title": "City Libraries", "text": ARTICLE})
        self.assertEqual(created.status_code, 201)
        article_id = created.json()["article_id"]

        listing = await self.client.get("/api/articles")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json(), [
            {"id": db.SAMPLE_ARTICLE_ID, "title": "Venus and Adonis", "built_in": True},
            {"id": article_id, "title": "City Libraries", "built_in": False},
        ])
        article = await self.client.get(f"/api/articles/{article_id}")
        self.assertEqual(article.status_code, 200)
        stages = article.json()["stages"]
        self.assertEqual(" ".join(stage["passage"] for stage in stages).split(), ARTICLE.split())
        for stage in stages:
            self.assertEqual(set(stage["question"]), {"title", "prompt", "options"})
        self.assertEqual((await self.client.get("/api/articles/missing")).status_code, 404)
        with db.transaction() as connection:
            self.assertEqual(connection.scalar(select(func.count()).select_from(db.sessions)), 0)
        self.assertEqual(self.provider.calls, 1)

    async def test_saved_article_can_be_replayed_with_fresh_progress(self):
        created = await self.client.post("/api/articles", json={"text": ARTICLE})
        self.assertEqual(created.status_code, 201)
        selection = created.json()
        first = (await self.client.post("/api/sessions", json=selection)).json()
        first_url = f"/api/sessions/{first['session_id']}"
        snapshot = (await self.client.get(first_url)).json()
        answer = await self.client.post(f"{first_url}/answers", json={
            "challenge_id": snapshot["article"]["stages"][0]["id"],
            "selected_option_id": "B",
            "request_id": "first-answer",
        })
        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.json()["xp"], 10)

        replay = (await self.client.post("/api/sessions", json=selection)).json()
        self.assertNotEqual(replay["session_id"], first["session_id"])
        fresh = (await self.client.get(f"/api/sessions/{replay['session_id']}")).json()
        self.assertEqual(fresh["article"], snapshot["article"])
        self.assertEqual(fresh["xp"], 0)
        self.assertEqual(fresh["completed_stages"], 0)
        self.assertEqual(fresh["answers"], [])
        self.assertEqual((await self.client.get(first_url)).json()["xp"], 10)
        self.assertEqual(self.provider.calls, 1)

    async def test_invalid_tool_calls_and_provider_failure_fall_back_to_retry(self):
        for call in (
            None,
            ToolCall("complete", {"skill": "Main Idea"}),
            ToolCall("give_hint", {"description": "Give a hint"}),
            ToolCall("give_hint", {"skill": "Sentence Puzzle"}),
            ProviderTimeout("Timed out"),
        ):
            with self.subTest(call=call):
                session = (await self.client.post("/api/sessions")).json()
                with patch.object(self.provider, "request_tool_call", side_effect=[call]):
                    response = await self.client.post(
                        f"/api/sessions/{session['session_id']}/answers",
                        json={"challenge_id": "the-warning", "selected_option_id": "A",
                              "request_id": "first-attempt"},
                    )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["agent_action"], "RETRY")
                self.assertTrue(response.json()["retry_allowed"])

    async def test_concurrent_attempt_discards_a_hint_based_on_stale_state(self):
        session = (await self.client.post("/api/sessions")).json()

        def first_attempt(**_kwargs):
            # Simulate another request committing a miss while this request waits for Gemini.
            submit_answer(
                UUID(session["session_id"]),
                AnswerSubmission(
                    challenge_id="the-warning", selected_option_id="A", request_id="other-request",
                ),
                FakeProvider(),
            )
            return ToolCall("give_hint", {"skill": "Main Idea"})

        with patch.object(self.provider, "request_tool_call", side_effect=first_attempt):
            response = await self.client.post(
                f"/api/sessions/{session['session_id']}/answers",
                json={"challenge_id": "the-warning", "selected_option_id": "C",
                      "request_id": "original-request"},
            )
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.assertEqual(answer["attempt_number"], 2)
        self.assertEqual(answer["agent_action"], "NEXT_CHALLENGE")
        self.assertFalse(answer["retry_allowed"])
        self.assertEqual(answer["completed_stages"], 1)

    async def test_short_article_is_rejected_before_model_call(self):
        response = await self.client.post("/api/articles", json={"text": "Too short."})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.provider.calls, 0)

    async def test_invalid_output_does_not_save_an_article_or_questions(self):
        for defect in ("wrong passage", "duplicate options", "invalid answer ID"):
            with self.subTest(defect=defect):
                self.provider.defect = defect
                response = await self.client.post("/api/articles", json={"text": ARTICLE})
                self.assertEqual(response.status_code, 502)
                with db.transaction() as connection:
                    self.assertEqual(connection.scalar(select(func.count()).select_from(db.articles)), 1)
                    self.assertEqual(connection.scalar(select(func.count()).select_from(db.challenges)), 3)

    async def test_single_blank_variants_are_normalized(self):
        for blank in ("___", "______", "[BLANK]"):
            with self.subTest(blank=blank):
                self.provider.puzzle = f"The city opened a new {blank}."
                response = await self.client.post("/api/articles", json={"text": ARTICLE})
                self.assertEqual(response.status_code, 201)
                with db.transaction() as connection:
                    prompt = connection.execute(
                        select(db.challenges.c.prompt).where(
                            db.challenges.c.article_id == response.json()["article_id"],
                            db.challenges.c.challenge_id == "sentence-puzzle",
                        )
                    ).scalar_one()
                self.assertEqual(prompt, "The city opened a new _____.")

    async def test_missing_or_multiple_blanks_do_not_save_an_article(self):
        for prompt in ("The city opened a new library.", "The city ___ a new [blank]."):
            with self.subTest(prompt=prompt):
                self.provider.puzzle = prompt
                response = await self.client.post("/api/articles", json={"text": ARTICLE})
                self.assertEqual(response.status_code, 502)
                with db.transaction() as connection:
                    self.assertEqual(connection.scalar(select(func.count()).select_from(db.articles)), 1)

    async def test_provider_errors_return_actionable_responses(self):
        cases = ((ProviderTimeout("Try again."), 504), (ProviderUnavailable("Try later."), 503))
        for error, status in cases:
            with self.subTest(status=status), patch.object(self.provider, "generate_json", side_effect=error):
                response = await self.client.post("/api/articles", json={"text": ARTICLE})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), {"detail": str(error)})
