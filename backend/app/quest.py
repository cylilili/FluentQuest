from dataclasses import dataclass, field
from threading import Lock
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, StringConstraints

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


@dataclass(frozen=True)
class Challenge:
    correct_option_id: OptionId
    explanation: str


# A, B, and C match the displayed option order in the built-in quest.
CHALLENGES = {
    "the-warning": Challenge(
        "B", "Venus enjoys hunting with Adonis and asks him to stay away from dangerous animals."
    ),
    "the-hunt": Challenge(
        "C", "To heed a warning is to take it seriously and act on it. Adonis ignored the warning."
    ),
    "the-windflower": Challenge(
        "A", "Because introduces the reason Venus turned around. She heard Adonis cry out."
    ),
}


@dataclass
class QuestSession:
    session_id: UUID
    attempts: dict[str, int] = field(default_factory=dict)
    completed: set[str] = field(default_factory=set)
    submissions: dict[str, tuple[AnswerSubmission, AnswerResult]] = field(default_factory=dict)
    xp: int = 0

    def progress(self) -> SessionProgress:
        return SessionProgress(
            session_id=self.session_id,
            xp=self.xp,
            completed_stages=len(self.completed),
            total_stages=len(CHALLENGES),
            session_completed=len(self.completed) == len(CHALLENGES),
        )


sessions: dict[UUID, QuestSession] = {}
sessions_lock = Lock()


def create_session() -> SessionProgress:
    session = QuestSession(session_id=uuid4())
    with sessions_lock:
        sessions[session.session_id] = session
    return session.progress()


def submit_answer(session_id: UUID, submission: AnswerSubmission) -> AnswerResult:
    # Replay checks, grading, and progress updates must happen as one operation.
    with sessions_lock:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Quest session not found")

        previous = session.submissions.get(submission.request_id)
        if previous is not None:
            original, result = previous
            if original != submission:
                raise HTTPException(
                    status_code=409, detail="Request ID already used for a different answer"
                )
            return result

        challenge_id = submission.challenge_id
        challenge = CHALLENGES.get(challenge_id)
        if challenge is None:
            raise HTTPException(status_code=404, detail="Challenge not found")
        if challenge_id in session.completed:
            raise HTTPException(status_code=409, detail="Challenge already completed")

        attempt = session.attempts.get(challenge_id, 0) + 1
        correct = submission.selected_option_id == challenge.correct_option_id
        retry_allowed = not correct and attempt < MAX_ATTEMPTS
        xp_awarded = XP_PER_CORRECT_ANSWER if correct else 0

        session.attempts[challenge_id] = attempt
        session.xp += xp_awarded
        if not retry_allowed:
            session.completed.add(challenge_id)

        feedback = (
            "Read the passage again and try another option."
            if retry_allowed
            else challenge.explanation
        )
        result = AnswerResult(
            **session.progress().model_dump(),
            challenge_id=challenge_id,
            correct=correct,
            attempt_number=attempt,
            retry_allowed=retry_allowed,
            challenge_completed=not retry_allowed,
            xp_awarded=xp_awarded,
            feedback=feedback,
        )
        session.submissions[submission.request_id] = (submission, result)
        return result
