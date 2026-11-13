from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from .db import SAMPLE_ARTICLE_ID, articles, challenges, sessions, submissions, transaction

OptionId = Literal["A", "B", "C"]
MAX_ATTEMPTS = 2
XP_PER_CORRECT_ANSWER = 10


class AnswerSubmission(BaseModel):
    challenge_id: str
    selected_option_id: OptionId
    request_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]


class SessionProgress(BaseModel):
    session_id: UUID
    xp: int
    completed_stages: int
    total_stages: int
    session_completed: bool


class AnswerResult(SessionProgress):
    challenge_id: str
    correct: bool
    attempt_number: int
    retry_allowed: bool
    challenge_completed: bool
    xp_awarded: int
    feedback: str


class SubmittedAnswer(AnswerResult):
    selected_option_id: OptionId
    request_id: str


class Option(BaseModel):
    id: OptionId
    text: str


class Question(BaseModel):
    title: str
    prompt: str
    options: list[Option]


class Stage(BaseModel):
    id: str
    title: str
    passage: str
    question: Question


class ArticleSource(BaseModel):
    label: str
    url: str


class QuestArticle(BaseModel):
    id: str
    title: str
    source: ArticleSource
    stages: list[Stage]


class SessionSnapshot(SessionProgress):
    article: QuestArticle
    answers: list[SubmittedAnswer]


def load_session(connection: Connection, session_id: UUID):
    session = connection.execute(
        select(sessions).where(sessions.c.id == str(session_id))
    ).one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Quest session not found")
    return session


def count_stages(connection: Connection, article_id: str) -> int:
    return connection.execute(
        select(func.count()).select_from(challenges).where(challenges.c.article_id == article_id)
    ).scalar_one()


def make_progress(
    session_id: UUID, xp: int, completed_stages: int, total_stages: int
) -> SessionProgress:
    return SessionProgress(
        session_id=session_id,
        xp=xp,
        completed_stages=completed_stages,
        total_stages=total_stages,
        session_completed=completed_stages == total_stages,
    )


def create_session() -> SessionProgress:
    session_id = uuid4()
    with transaction(write=True) as connection:
        connection.execute(
            sessions.insert().values(
                id=str(session_id), article_id=SAMPLE_ARTICLE_ID, xp=0, completed_stages=0
            )
        )
        total_stages = count_stages(connection, SAMPLE_ARTICLE_ID)
    return make_progress(session_id, 0, 0, total_stages)


def get_session(session_id: UUID) -> SessionSnapshot:
    with transaction() as connection:
        session = load_session(connection, session_id)
        article = connection.execute(
            select(articles).where(articles.c.id == session.article_id)
        ).one()
        stage_rows = connection.execute(
            select(
                challenges.c.challenge_id,
                challenges.c.title,
                challenges.c.passage,
                challenges.c.question_type,
                challenges.c.prompt,
                challenges.c.options,
            )
            .where(challenges.c.article_id == article.id)
            .order_by(challenges.c.position)
        ).all()
        answer_rows = connection.execute(
            select(submissions.c.selected_option_id, submissions.c.request_id, submissions.c.result)
            .where(submissions.c.session_id == session.id)
            .order_by(submissions.c.challenge_id, submissions.c.attempt_number)
        ).all()

    progress = make_progress(session_id, session.xp, session.completed_stages, len(stage_rows))
    return SessionSnapshot(
        **progress.model_dump(),
        article=QuestArticle(
            id=article.id,
            title=article.title,
            source=article.source,
            stages=[
                Stage(
                    id=stage.challenge_id,
                    title=stage.title,
                    passage=stage.passage,
                    question=Question(
                        title=stage.question_type, prompt=stage.prompt, options=stage.options
                    ),
                )
                for stage in stage_rows
            ],
        ),
        answers=[
            SubmittedAnswer(
                **answer.result,
                selected_option_id=answer.selected_option_id,
                request_id=answer.request_id,
            )
            for answer in answer_rows
        ],
    )


def submit_answer(session_id: UUID, submission: AnswerSubmission) -> AnswerResult:
    with transaction(write=True) as connection:
        session = load_session(connection, session_id)
        previous = connection.execute(
            select(challenges.c.challenge_id, submissions.c.selected_option_id, submissions.c.result)
            .join_from(submissions, challenges)
            .where(
                submissions.c.session_id == session.id,
                submissions.c.request_id == submission.request_id,
            )
        ).one_or_none()
        if previous is not None:
            if (previous.challenge_id, previous.selected_option_id) != (
                submission.challenge_id,
                submission.selected_option_id,
            ):
                raise HTTPException(
                    status_code=409, detail="Request ID already used for a different answer"
                )
            return AnswerResult.model_validate(previous.result)

        challenge = connection.execute(
            select(challenges).where(
                challenges.c.article_id == session.article_id,
                challenges.c.challenge_id == submission.challenge_id,
            )
        ).one_or_none()
        if challenge is None:
            raise HTTPException(status_code=404, detail="Challenge not found")

        latest = connection.execute(
            select(submissions.c.attempt_number, submissions.c.result)
            .where(
                submissions.c.session_id == session.id,
                submissions.c.challenge_id == challenge.id,
            )
            .order_by(submissions.c.attempt_number.desc())
            .limit(1)
        ).one_or_none()
        if latest is not None and latest.result["challenge_completed"]:
            raise HTTPException(status_code=409, detail="Challenge already completed")

        attempt = 1 if latest is None else latest.attempt_number + 1
        correct = submission.selected_option_id == challenge.correct_option_id
        retry_allowed = not correct and attempt < MAX_ATTEMPTS
        xp_awarded = XP_PER_CORRECT_ANSWER if correct else 0
        progress = make_progress(
            session_id,
            session.xp + xp_awarded,
            session.completed_stages + int(not retry_allowed),
            count_stages(connection, session.article_id),
        )
        result = AnswerResult(
            **progress.model_dump(),
            challenge_id=submission.challenge_id,
            correct=correct,
            attempt_number=attempt,
            retry_allowed=retry_allowed,
            challenge_completed=not retry_allowed,
            xp_awarded=xp_awarded,
            feedback=(
                "Read the passage again and try another option."
                if retry_allowed
                else challenge.explanation
            ),
        )

        connection.execute(
            sessions.update()
            .where(sessions.c.id == session.id)
            .values(xp=progress.xp, completed_stages=progress.completed_stages)
        )
        connection.execute(
            submissions.insert().values(
                session_id=session.id,
                request_id=submission.request_id,
                challenge_id=challenge.id,
                selected_option_id=submission.selected_option_id,
                attempt_number=attempt,
                result=result.model_dump(mode="json"),
            )
        )
    return result
