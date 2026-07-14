from __future__ import annotations

import asyncio

import pytest

from chess_tui.sessions.demo import DemoQuizSession, list_demo_flows
from chess_tui.sessions.errors import SessionUnavailableError
from chess_tui.sessions.models import MoveChoice, QuizPhase, QuizQuestion


def test_question_rejects_duplicate_choice_ids() -> None:
    choice = MoveChoice("a", "d4", "d2d4")

    with pytest.raises(ValueError, match="unique"):
        QuizQuestion("root", "Move", (choice, choice))


def test_demo_flows_load_and_validate() -> None:
    flows = list_demo_flows()

    assert [(flow.name, flow.side) for flow in flows] == [
        ("London Demo", "white"),
        ("Caro-Kann Demo", "black"),
    ]


def test_demo_session_correct_and_mismatch_feedback() -> None:
    async def run_test() -> None:
        correct_session = DemoQuizSession()
        root = await correct_session.start()
        assert root.phase is QuizPhase.QUESTION
        assert root.line_san == ()
        assert root.question is not None
        assert not hasattr(root.question, "correct")

        correct = await correct_session.answer(root.question.id, "s")
        assert correct.phase is QuizPhase.CORRECT_FEEDBACK
        assert correct.feedback is not None and correct.feedback.correct

        mismatch_session = DemoQuizSession()
        mismatch_root = await mismatch_session.start()
        assert mismatch_root.question is not None
        mismatch = await mismatch_session.answer(mismatch_root.question.id, "a")
        assert mismatch.phase is QuizPhase.MISMATCH_FEEDBACK
        assert mismatch.feedback is not None and not mismatch.feedback.correct

        next_after_correct = await correct_session.continue_session()
        next_after_mismatch = await mismatch_session.continue_session()
        assert next_after_correct.fen == next_after_mismatch.fen
        assert next_after_correct.line_san == ("d4", "d5")

    asyncio.run(run_test())


def test_demo_session_reaches_frontier_and_restarts() -> None:
    async def run_test() -> None:
        session = DemoQuizSession()
        state = await session.start()
        for choice_id in ("s", "a", "a"):
            assert state.question is not None
            await session.answer(state.question.id, choice_id)
            state = await session.continue_session()

        assert state.phase is QuizPhase.FRONTIER
        assert state.frontier is not None
        assert state.line_san == ("d4", "d5", "Bf4", "Nf6", "Nf3")

        restarted = await session.restart()
        assert restarted.phase is QuizPhase.QUESTION
        assert restarted.line_san == ()

    asyncio.run(run_test())


def test_demo_sessions_do_not_share_state() -> None:
    async def run_test() -> None:
        first = DemoQuizSession()
        second = DemoQuizSession()
        first_state = await first.start()
        second_state = await second.start()
        assert first_state.question is not None

        await first.answer(first_state.question.id, "s")
        advanced = await first.continue_session()

        assert advanced.line_san == ("d4", "d5")
        assert second_state.line_san == ()
        assert second_state.phase is QuizPhase.QUESTION

    asyncio.run(run_test())


def test_unknown_demo_fixture_fails_loudly() -> None:
    with pytest.raises(SessionUnavailableError, match="Unknown demo flow"):
        DemoQuizSession("missing")
