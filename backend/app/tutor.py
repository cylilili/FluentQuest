from enum import StrEnum
from typing import Literal, TypedDict

from pydantic import BaseModel


class TutorAction(StrEnum):
    GIVE_HINT = "GIVE_HINT"
    SIMPLIFY = "SIMPLIFY"
    RETRY = "RETRY"
    NEXT_CHALLENGE = "NEXT_CHALLENGE"
    COMPLETE = "COMPLETE"


class TutorState(TypedDict):
    """The state of one submission after server-side grading."""

    session_id: str
    article_id: str
    challenge_id: str
    skill_tag: str
    attempt_number: int
    correct: bool
    retry_allowed: bool
    session_completed: bool


TutorTool = Literal["give_hint", "show_simpler_example"]
TutorReason = Literal[
    "correct_answer",
    "no_available_tool",
    "tool_accepted",
    "no_tool_call",
    "invalid_tool_call",
    "provider_timeout",
    "provider_unavailable",
    "invalid_provider_response",
]


class TutorTrace(BaseModel):
    input_state: TutorState
    nodes: list[Literal["choose_action", "give_hint", "show_simpler_example"]]
    offered_tool: TutorTool | None
    requested_tool: TutorTool | None
    reason: TutorReason
    action: TutorAction
    applied: bool = True


def allowed_tutor_actions(state: TutorState) -> tuple[TutorAction, ...]:
    """Return legal actions with the deterministic fallback first."""
    if state["retry_allowed"]:
        return TutorAction.RETRY, TutorAction.GIVE_HINT

    progression = (
        TutorAction.COMPLETE if state["session_completed"] else TutorAction.NEXT_CHALLENGE
    )
    if state["correct"]:
        return (progression,)

    # Remedial feedback does not reopen the core challenge.
    return progression, TutorAction.SIMPLIFY


def resolve_tutor_action(
    state: TutorState, proposed_action: TutorAction | None
) -> TutorAction:
    actions = allowed_tutor_actions(state)
    if proposed_action is not None and proposed_action in actions:
        return proposed_action
    return actions[0]
