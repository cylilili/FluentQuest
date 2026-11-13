import json
import logging
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from .llm import LLMProvider, ProviderResponseError, ProviderTimeout, ProviderUnavailable
from .tutor import (
    HintLevel,
    SkillHistory,
    TutorAction,
    TutorReason,
    TutorState,
    TutorTool,
    TutorTrace,
    allowed_tutor_actions,
    resolve_tutor_action,
)


logger = logging.getLogger(__name__)
HINT_TOOL = "give_hint"
SIMPLIFY_TOOL = "show_simpler_example"
HINTS = {
    "Main Idea": "Look for the idea that connects the details across the whole passage.",
    "Vocabulary in Context": "Read the sentences around the expression for clues to its meaning.",
    "Sentence Puzzle": "Read the words before and after the blank, then try each option in place.",
}
GUIDED_HINTS = {
    "Main Idea": (
        "Find two details that point to the same message. "
        "Then rule out options that describe only one detail or add an idea the passage never mentions."
    ),
    "Vocabulary in Context": (
        "Read the sentence before and after the unfamiliar expression. "
        "Look for a clue such as a contrast or an example, then replace the expression with each option."
    ),
    "Sentence Puzzle": (
        "Decide what the blank needs, such as a verb or a word linking two ideas. "
        "Then read the whole sentence with each option and check both meaning and grammar."
    ),
}
SIMPLER_EXAMPLES = {
    "Main Idea": (
        "Mia watered the plants and pulled weeds. "
        "Both details support one main idea: Mia took care of the garden."
    ),
    "Vocabulary in Context": (
        "Leo was exhausted. He could barely keep his eyes open. "
        "The second sentence tells you that exhausted means very tired."
    ),
    "Sentence Puzzle": (
        "Try ‘She _____ a photo’ with ‘took’ and ‘made.’ "
        "‘Took a photo’ is the usual expression in English."
    ),
}


class TutorGraphState(TypedDict):
    answer: TutorState
    skill_history: SkillHistory | None
    action: NotRequired[TutorAction]
    feedback: NotRequired[str]
    reason: NotRequired[TutorReason]
    offered_tool: NotRequired[TutorTool]
    requested_tool: NotRequired[TutorTool | None]
    executed_tool: NotRequired[TutorTool]
    hint_level: NotRequired[HintLevel]


@dataclass(frozen=True)
class TutorContext:
    provider: LLMProvider


@dataclass(frozen=True)
class TutorDecision:
    trace: TutorTrace
    feedback: str | None = None


def choose_action(state: TutorGraphState, runtime: Runtime[TutorContext]) -> dict:
    answer = state["answer"]
    actions = allowed_tutor_actions(answer)
    skill = answer["skill_tag"]
    if TutorAction.GIVE_HINT in actions:
        action = TutorAction.GIVE_HINT
        tool_name = HINT_TOOL
        tool_description = "Give a reading strategy for this skill without revealing the answer."
    elif TutorAction.SIMPLIFY in actions and skill in SIMPLER_EXAMPLES:
        action = TutorAction.SIMPLIFY
        tool_name = SIMPLIFY_TOOL
        tool_description = "Show a simpler worked example of the same reading skill after the final miss."
    else:
        return {
            "action": actions[0],
            "reason": "correct_answer" if answer["correct"] else "no_available_tool",
        }

    proposed = None
    requested_tool = None
    reason: TutorReason
    try:
        call = runtime.context.provider.request_tool_call(
            instructions=(
                "You are a reading tutor. The learner missed a question. "
                "Prefer calling the available tool to help with the current reading skill. "
                "Pass the skill exactly as provided. Reply CONTINUE if the tool would not help."
            ),
            content=json.dumps({
                "skill": skill,
                "attempt": answer["attempt_number"],
                "retry_allowed": answer["retry_allowed"],
            }),
            tool_name=tool_name,
            tool_description=tool_description,
            tool_parameters={
                "type": "OBJECT",
                "properties": {
                    "skill": {
                        "type": "STRING",
                        "description": "The reading skill of the current question.",
                        "enum": [skill],
                    },
                },
                "required": ["skill"],
            },
        )
    except (ProviderUnavailable, ProviderTimeout, ProviderResponseError) as exc:
        logger.warning("Tutor used %s because the provider failed (%s): %s", actions[0], type(exc).__name__, exc)
        if isinstance(exc, ProviderTimeout):
            reason = "provider_timeout"
        elif isinstance(exc, ProviderResponseError):
            reason = "invalid_provider_response"
        else:
            reason = "provider_unavailable"
    else:
        if call is None:
            reason = "no_tool_call"
        elif call.name == tool_name and call.arguments == {"skill": skill}:
            proposed = action
            reason = "tool_accepted"
        else:
            reason = "invalid_tool_call"
            logger.warning("Tutor used %s because the tool name or arguments were invalid", actions[0])

        # Record recognized names only. Model output can contain arbitrary strings.
        if call is not None and call.name in (HINT_TOOL, SIMPLIFY_TOOL):
            requested_tool = call.name

    return {
        "action": resolve_tutor_action(answer, proposed),
        "reason": reason,
        "offered_tool": tool_name,
        "requested_tool": requested_tool,
    }


def give_hint(state: TutorGraphState) -> dict:
    skill = state["answer"]["skill_tag"]
    history = state["skill_history"]
    if history is not None and history.needs_guidance() and skill in GUIDED_HINTS:
        return {
            "executed_tool": HINT_TOOL,
            "hint_level": "guided",
            "feedback": GUIDED_HINTS[skill],
        }

    return {
        "executed_tool": HINT_TOOL,
        "hint_level": "standard",
        "feedback": HINTS.get(
            skill,
            "Reread the passage and look for a detail that supports your choice.",
        ),
    }


def show_simpler_example(state: TutorGraphState) -> dict:
    return {
        "executed_tool": SIMPLIFY_TOOL,
        "feedback": SIMPLER_EXAMPLES[state["answer"]["skill_tag"]],
    }


def route_action(state: TutorGraphState) -> Literal["give_hint", "show_simpler_example", "__end__"]:
    if state["action"] == TutorAction.GIVE_HINT:
        return HINT_TOOL
    if state["action"] == TutorAction.SIMPLIFY:
        return SIMPLIFY_TOOL
    return END


tutor_graph = (
    StateGraph(TutorGraphState, context_schema=TutorContext)
    .add_node("choose_action", choose_action)
    .add_node(HINT_TOOL, give_hint)
    .add_node(SIMPLIFY_TOOL, show_simpler_example)
    .add_edge(START, "choose_action")
    .add_conditional_edges("choose_action", route_action)
    .add_edge(HINT_TOOL, END)
    .add_edge(SIMPLIFY_TOOL, END)
    .compile()
)


def run_tutor(
    answer: TutorState, provider: LLMProvider, *, skill_history: SkillHistory | None = None
) -> TutorDecision:
    result = tutor_graph.invoke(
        {"answer": answer, "skill_history": skill_history},
        context=TutorContext(provider),
    )
    executed_tool = result.get("executed_tool")
    nodes = ["choose_action"]
    if executed_tool is not None:
        nodes.append(executed_tool)
    trace = TutorTrace(
        input_state=answer,
        nodes=nodes,
        offered_tool=result.get("offered_tool"),
        requested_tool=result.get("requested_tool"),
        reason=result["reason"],
        action=result["action"],
        skill_history=skill_history,
        hint_level=result.get("hint_level"),
    )
    return TutorDecision(trace=trace, feedback=result.get("feedback"))
