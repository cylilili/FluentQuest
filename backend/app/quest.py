from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from .db import SAMPLE_ARTICLE_ID, articles, challenges, sessions, submissions, transaction
from .llm import LLMProvider
from .tutor import TutorAction, TutorState, TutorTrace, resolve_tutor_action
from .tutor_graph import run_tutor

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
    agent_action: TutorAction | None = None
    agent_trace: TutorTrace | None = None


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


class ArticleListItem(BaseModel):
    id: str
    title: str
    built_in: bool


class QuestArticle(BaseModel):
    id: str
    title: str
    source: ArticleSource | None
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


def create_session(article_id: str = SAMPLE_ARTICLE_ID) -> SessionProgress:
    session_id = uuid4()
    with transaction(write=True) as connection:
        total_stages = count_stages(connection, article_id)
        if total_stages == 0:
            raise HTTPException(status_code=404, detail="Quest article not found")
        connection.execute(
            sessions.insert().values(
                id=str(session_id), article_id=article_id, xp=0, completed_stages=0
            )
        )
    return make_progress(session_id, 0, 0, total_stages)


def list_articles() -> list[ArticleListItem]:
    with transaction() as connection:
        rows = connection.execute(
            select(articles.c.id, articles.c.title).order_by(
                (articles.c.id == SAMPLE_ARTICLE_ID).desc(), func.lower(articles.c.title), articles.c.id
            )
        ).all()
    return [
        ArticleListItem(id=row.id, title=row.title, built_in=row.id == SAMPLE_ARTICLE_ID)
        for row in rows
    ]


def load_article(connection: Connection, article_id: str) -> QuestArticle:
    article = connection.execute(
        select(articles).where(articles.c.id == article_id)
    ).one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Quest article not found")

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
    return QuestArticle(
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
    )


def get_article(article_id: str) -> QuestArticle:
    with transaction() as connection:
        return load_article(connection, article_id)


def get_session(session_id: UUID) -> SessionSnapshot:
    with transaction() as connection:
        session = load_session(connection, session_id)
        article = load_article(connection, session.article_id)
        answer_rows = connection.execute(
            select(submissions.c.selected_option_id, submissions.c.request_id, submissions.c.result)
            .where(submissions.c.session_id == session.id)
            .order_by(submissions.c.challenge_id, submissions.c.attempt_number)
        ).all()

    progress = make_progress(session_id, session.xp, session.completed_stages, len(article.stages))
    return SessionSnapshot(
        **progress.model_dump(),
        article=article,
        answers=[
            SubmittedAnswer(
                **answer.result,
                selected_option_id=answer.selected_option_id,
                request_id=answer.request_id,
            )
            for answer in answer_rows
        ],
    )


def load_saved_answer(
    connection: Connection, session_id: UUID, submission: AnswerSubmission
) -> AnswerResult | None:
    previous = connection.execute(
        select(challenges.c.challenge_id, submissions.c.selected_option_id, submissions.c.result)
        .join_from(submissions, challenges)
        .where(
            submissions.c.session_id == str(session_id),
            submissions.c.request_id == submission.request_id,
        )
    ).one_or_none()
    if previous is None:
        return None
    if (previous.challenge_id, previous.selected_option_id) != (
        submission.challenge_id, submission.selected_option_id
    ):
        raise HTTPException(status_code=409, detail="Request ID already used for a different answer")
    return AnswerResult.model_validate(previous.result)


def grade_answer(
    connection: Connection, session_id: UUID, submission: AnswerSubmission
) -> tuple[int, TutorState, AnswerResult]:
    session = load_session(connection, session_id)
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
        .where(submissions.c.session_id == session.id, submissions.c.challenge_id == challenge.id)
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
    state: TutorState = {
        "session_id": session.id,
        "article_id": session.article_id,
        "challenge_id": submission.challenge_id,
        "skill_tag": challenge.question_type,
        "attempt_number": attempt,
        "correct": correct,
        "retry_allowed": retry_allowed,
        "session_completed": progress.session_completed,
    }
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
    return challenge.id, state, result


def submit_answer(
    session_id: UUID, submission: AnswerSubmission, provider: LLMProvider
) -> AnswerResult:
    with transaction() as connection:
        previous = load_saved_answer(connection, session_id, submission)
        if previous is not None:
            return previous
        _, state, _ = grade_answer(connection, session_id, submission)

    decision = run_tutor(state, provider)

    with transaction(write=True) as connection:
        previous = load_saved_answer(connection, session_id, submission)
        if previous is not None:
            return previous

        # Another submission may have changed the attempt or progress during the model call.
        challenge_id, current_state, result = grade_answer(connection, session_id, submission)
        applied = current_state == state
        result.agent_trace = decision.trace.model_copy(update={"applied": applied})
        result.agent_action = decision.trace.action if applied else resolve_tutor_action(current_state, None)
        if applied and result.agent_action == TutorAction.SIMPLIFY and decision.feedback is not None:
            result.feedback += f"\n\nSimpler example\n{decision.feedback}"
        elif applied and decision.feedback is not None:
            result.feedback = decision.feedback

        connection.execute(
            sessions.update()
            .where(sessions.c.id == str(session_id))
            .values(xp=result.xp, completed_stages=result.completed_stages)
        )
        connection.execute(
            submissions.insert().values(
                session_id=str(session_id),
                request_id=submission.request_id,
                challenge_id=challenge_id,
                selected_option_id=submission.selected_option_id,
                attempt_number=result.attempt_number,
                result=result.model_dump(mode="json"),
            )
        )
    return result
