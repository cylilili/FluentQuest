import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import URL

from app import db
from app.llm import ProviderTimeout, ProviderUnavailable, get_llm_provider
from app.main import app

ARTICLE = "\n\n".join(
    " ".join(f"The city opened a new library in district {index}." for index in group)
    for group in (range(1, 13), range(13, 25), range(25, 37))
)


class FakeProvider:
    def __init__(self):
        self.defect = None
        self.puzzle = "The city opened a new _____."
        self.calls = 0

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
