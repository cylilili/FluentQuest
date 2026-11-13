import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import URL

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "reading_quest.sqlite3"
SAMPLE_QUEST_PATH = Path(__file__).with_name("sample_quest.json")
SAMPLE_ARTICLE_ID = "venus-and-adonis-v1"

engine = create_engine(
    URL.create("sqlite", database=str(DATABASE_PATH)),
    connect_args={"autocommit": sqlite3.LEGACY_TRANSACTION_CONTROL},
)


@event.listens_for(engine, "connect")
def enable_foreign_keys(connection, _record):
    connection.execute("PRAGMA foreign_keys = ON").close()


metadata = MetaData()

articles = Table(
    "articles",
    metadata,
    Column("id", String, primary_key=True),
    Column("title", String, nullable=False),
    Column("source", JSON, nullable=False),
)

challenges = Table(
    "challenges",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("article_id", ForeignKey("articles.id"), nullable=False),
    Column("challenge_id", String, nullable=False),
    Column("position", Integer, nullable=False),
    Column("title", String, nullable=False),
    Column("passage", Text, nullable=False),
    Column("question_type", String, nullable=False),
    Column("prompt", Text, nullable=False),
    Column("options", JSON, nullable=False),
    Column("correct_option_id", String, nullable=False),
    Column("explanation", Text, nullable=False),
    UniqueConstraint("article_id", "challenge_id"),
    UniqueConstraint("article_id", "position"),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", String, primary_key=True),
    Column("article_id", ForeignKey("articles.id"), nullable=False),
    Column("xp", Integer, nullable=False),
    Column("completed_stages", Integer, nullable=False),
)

submissions = Table(
    "submissions",
    metadata,
    Column("session_id", ForeignKey("sessions.id"), primary_key=True),
    Column("request_id", String, primary_key=True),
    Column("challenge_id", ForeignKey("challenges.id"), nullable=False),
    Column("selected_option_id", String, nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("result", JSON, nullable=False),
    UniqueConstraint("session_id", "challenge_id", "attempt_number"),
)


@contextmanager
def transaction(*, write: bool = False):
    with engine.begin() as connection:
        # Reserve the write lock before reading state used to grade an answer.
        connection.exec_driver_sql("BEGIN IMMEDIATE" if write else "BEGIN")
        yield connection


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sample = json.loads(SAMPLE_QUEST_PATH.read_text(encoding="utf-8"))

    with transaction(write=True) as connection:
        metadata.create_all(connection)
        # Keep existing sessions tied to the same version of the sample questions.
        seeded = connection.execute(
            insert(articles)
            .values(id=SAMPLE_ARTICLE_ID, title=sample["title"], source=sample["source"])
            .on_conflict_do_nothing(index_elements=[articles.c.id])
        )
        if seeded.rowcount == 0:
            return

        connection.execute(
            challenges.insert(),
            [
                {
                    "article_id": SAMPLE_ARTICLE_ID,
                    "challenge_id": stage["id"],
                    "position": position,
                    "title": stage["title"],
                    "passage": stage["passage"],
                    "question_type": stage["question"]["title"],
                    "prompt": stage["question"]["prompt"],
                    "options": stage["question"]["options"],
                    "correct_option_id": stage["question"]["correct_option_id"],
                    "explanation": stage["question"]["explanation"],
                }
                for position, stage in enumerate(sample["stages"])
            ],
        )
