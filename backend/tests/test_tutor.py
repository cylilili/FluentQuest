import unittest

from app.tutor import TutorAction, TutorState, allowed_tutor_actions, resolve_tutor_action


FIRST_MISS: TutorState = {
    "session_id": "session-1",
    "article_id": "article-1",
    "challenge_id": "main-idea",
    "skill_tag": "main_idea",
    "attempt_number": 1,
    "correct": False,
    "retry_allowed": True,
    "session_completed": False,
}


class TutorPolicyTests(unittest.TestCase):
    def test_first_miss_allows_hint_and_retry(self):
        self.assertEqual(
            allowed_tutor_actions(FIRST_MISS),
            (TutorAction.RETRY, TutorAction.GIVE_HINT),
        )
        self.assertEqual(
            resolve_tutor_action(FIRST_MISS, TutorAction.GIVE_HINT), TutorAction.GIVE_HINT
        )
        for proposal in (TutorAction.NEXT_CHALLENGE, TutorAction.COMPLETE, None):
            with self.subTest(proposal=proposal):
                self.assertEqual(resolve_tutor_action(FIRST_MISS, proposal), TutorAction.RETRY)

    def test_exhausted_attempts_allow_simplification_without_retry(self):
        state: TutorState = {**FIRST_MISS, "attempt_number": 2, "retry_allowed": False}
        self.assertEqual(
            allowed_tutor_actions(state), (TutorAction.NEXT_CHALLENGE, TutorAction.SIMPLIFY)
        )
        self.assertEqual(resolve_tutor_action(state, TutorAction.SIMPLIFY), TutorAction.SIMPLIFY)
        self.assertEqual(
            resolve_tutor_action(state, TutorAction.RETRY), TutorAction.NEXT_CHALLENGE
        )

    def test_correct_answer_advances_until_the_session_is_complete(self):
        state: TutorState = {**FIRST_MISS, "correct": True, "retry_allowed": False}
        self.assertEqual(allowed_tutor_actions(state), (TutorAction.NEXT_CHALLENGE,))
        self.assertEqual(
            resolve_tutor_action(state, TutorAction.COMPLETE), TutorAction.NEXT_CHALLENGE
        )

        completed: TutorState = {**state, "session_completed": True}
        self.assertEqual(allowed_tutor_actions(completed), (TutorAction.COMPLETE,))

    def test_final_miss_can_get_remediation_and_still_finish_the_session(self):
        state: TutorState = {
            **FIRST_MISS,
            "attempt_number": 2,
            "retry_allowed": False,
            "session_completed": True,
        }
        self.assertEqual(
            allowed_tutor_actions(state), (TutorAction.COMPLETE, TutorAction.SIMPLIFY)
        )
        self.assertEqual(resolve_tutor_action(state, TutorAction.NEXT_CHALLENGE), TutorAction.COMPLETE)
