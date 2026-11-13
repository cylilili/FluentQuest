from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.engine import Connection

from .db import challenges, submissions, transaction
from .tutor import SkillHistory, TutorAction


class SkillProgress(BaseModel):
    skill_tag: str
    attempts: int
    correct_attempts: int
    first_attempts: int
    correct_first_attempts: int
    hints_shown: int
    retries_after_hint: int
    correct_retries_after_hint: int
    simpler_examples_shown: int


class LearningProgress(BaseModel):
    skills: list[SkillProgress]


def load_skill_history(connection: Connection, *, session_id: str, skill_tag: str) -> SkillHistory:
    incorrect = submissions.c.result["correct"].as_boolean().is_(False)
    counts = connection.execute(
        select(
            func.count().label("first_attempts"),
            func.count().filter(incorrect).label("incorrect_first_attempts"),
        )
        .select_from(submissions.join(challenges))
        .where(
            challenges.c.question_type == skill_tag,
            submissions.c.attempt_number == 1,
            submissions.c.session_id != session_id,
        )
    ).mappings().one()
    return SkillHistory.model_validate(counts)


def get_learning_progress() -> LearningProgress:
    # A retry belongs to the same question in the same playthrough.
    previous = submissions.alias("previous_attempt")
    previous_action = previous.c.result["agent_action"].as_string()
    action = submissions.c.result["agent_action"].as_string()
    correct = submissions.c.result["correct"].as_boolean().is_(True)
    first_attempt = submissions.c.attempt_number == 1
    after_hint = previous_action == TutorAction.GIVE_HINT
    skill = challenges.c.question_type

    summary = (
        select(
            skill.label("skill_tag"),
            func.count().label("attempts"),
            func.count().filter(correct).label("correct_attempts"),
            func.count().filter(first_attempt).label("first_attempts"),
            func.count().filter(first_attempt, correct).label("correct_first_attempts"),
            func.count().filter(action == TutorAction.GIVE_HINT).label("hints_shown"),
            func.count().filter(after_hint).label("retries_after_hint"),
            func.count().filter(after_hint, correct).label("correct_retries_after_hint"),
            func.count().filter(action == TutorAction.SIMPLIFY).label("simpler_examples_shown"),
        )
        .select_from(submissions.join(challenges))
        .outerjoin(
            previous,
            and_(
                previous.c.session_id == submissions.c.session_id,
                previous.c.challenge_id == submissions.c.challenge_id,
                previous.c.attempt_number == submissions.c.attempt_number - 1,
            ),
        )
        .group_by(skill)
        .order_by(skill)
    )
    with transaction() as connection:
        rows = connection.execute(summary).mappings().all()
    return LearningProgress(skills=[SkillProgress.model_validate(row) for row in rows])
