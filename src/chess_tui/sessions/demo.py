"""Strict local fixture-backed quiz sessions."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

from Chessnut import Game

from ..board import parse_fen
from .errors import SessionProtocolError, SessionUnavailableError
from .models import (
    FrontierState,
    MoveChoice,
    QuizFeedback,
    QuizPhase,
    QuizQuestion,
    QuizSessionState,
)

DEMO_FLOW_IDS = ("london-demo", "caro-kann-demo")


@dataclass(frozen=True, slots=True)
class DemoFlowSummary:
    id: str
    name: str
    side: str


@dataclass(frozen=True, slots=True)
class _DemoStep:
    id: str
    fen: str
    line_san: tuple[str, ...]
    prompt: str
    choices: tuple[MoveChoice, ...]
    correct_uci: str
    explanation: str | None
    advance_uci: tuple[str, ...]

    @property
    def question(self) -> QuizQuestion:
        return QuizQuestion(self.id, self.prompt, self.choices)

    @property
    def correct_choice(self) -> MoveChoice:
        return next(choice for choice in self.choices if choice.uci == self.correct_uci)


@dataclass(frozen=True, slots=True)
class _DemoFlow:
    summary: DemoFlowSummary
    steps: tuple[_DemoStep, ...]
    frontier_fen: str
    frontier_line: tuple[str, ...]


def list_demo_flows() -> tuple[DemoFlowSummary, ...]:
    return tuple(_load_flow(flow_id).summary for flow_id in DEMO_FLOW_IDS)


class DemoQuizSession:
    """Run one independent canonical demo flow from packaged TOML."""

    def __init__(self, flow_id: str = "london-demo") -> None:
        self.flow = _load_flow(flow_id)
        self._step_index = 0
        self._state: QuizSessionState | None = None
        self._closed = False

    async def start(self) -> QuizSessionState:
        self._require_open()
        self._step_index = 0
        self._state = self._question_state()
        return self._state

    async def answer(self, question_id: str, choice_id: str) -> QuizSessionState:
        self._require_open()
        if self._state is None or self._state.phase is not QuizPhase.QUESTION:
            raise SessionProtocolError("The session is not accepting an answer.")
        step = self.flow.steps[self._step_index]
        if question_id != step.id:
            raise SessionProtocolError(
                f"Stale question id {question_id!r}; expected {step.id!r}."
            )
        try:
            selected = next(choice for choice in step.choices if choice.id == choice_id)
        except StopIteration as exc:
            raise SessionProtocolError(f"Unknown choice id: {choice_id!r}.") from exc

        expected = step.correct_choice
        correct = selected.id == expected.id
        phase = QuizPhase.CORRECT_FEEDBACK if correct else QuizPhase.MISMATCH_FEEDBACK
        self._state = QuizSessionState(
            phase=phase,
            fen=step.fen,
            line_san=step.line_san,
            question=step.question,
            feedback=QuizFeedback(
                correct=correct,
                selected_san=selected.san,
                expected_san=expected.san,
                explanation=step.explanation,
            ),
        )
        return self._state

    async def continue_session(self) -> QuizSessionState:
        self._require_open()
        if self._state is None or self._state.phase not in {
            QuizPhase.CORRECT_FEEDBACK,
            QuizPhase.MISMATCH_FEEDBACK,
        }:
            raise SessionProtocolError("There is no feedback to continue from.")
        self._step_index += 1
        if self._step_index < len(self.flow.steps):
            self._state = self._question_state()
        else:
            self._state = QuizSessionState(
                phase=QuizPhase.FRONTIER,
                fen=self.flow.frontier_fen,
                line_san=self.flow.frontier_line,
                frontier=FrontierState(self.flow.frontier_line),
            )
        return self._state

    async def restart(self) -> QuizSessionState:
        return await self.start()

    async def close(self) -> None:
        self._closed = True
        self._state = None

    def _question_state(self) -> QuizSessionState:
        step = self.flow.steps[self._step_index]
        return QuizSessionState(
            phase=QuizPhase.QUESTION,
            fen=step.fen,
            line_san=step.line_san,
            question=step.question,
        )

    def _require_open(self) -> None:
        if self._closed:
            raise SessionUnavailableError("The demo session is closed.")


def _load_flow(flow_id: str) -> _DemoFlow:
    if flow_id not in DEMO_FLOW_IDS:
        raise SessionUnavailableError(f"Unknown demo flow: {flow_id!r}.")
    asset = resources.files("chess_tui").joinpath("assets", "quiz", f"{flow_id}.toml")
    try:
        data = tomllib.loads(asset.read_text(encoding="utf-8"))
        flow = _decode_flow(flow_id, data)
        _validate_flow(flow)
        return flow
    except FileNotFoundError as exc:
        raise SessionUnavailableError(
            f"Required demo fixture is missing: {flow_id}.toml"
        ) from exc
    except (KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise SessionProtocolError(
            f"Invalid demo fixture {flow_id}.toml: {exc}"
        ) from exc


def _decode_flow(flow_id: str, data: dict[str, Any]) -> _DemoFlow:
    raw_steps = data["states"]
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("states must be a non-empty array")
    steps: list[_DemoStep] = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            raise TypeError("each state must be a table")
        raw_choices = raw_step["choices"]
        if not isinstance(raw_choices, list):
            raise TypeError("state choices must be an array")
        choices = tuple(
            MoveChoice(
                id=_text(raw_choice, "id"),
                san=_text(raw_choice, "san"),
                uci=_text(raw_choice, "uci"),
            )
            for raw_choice in raw_choices
        )
        steps.append(
            _DemoStep(
                id=_text(raw_step, "id"),
                fen=_text(raw_step, "fen"),
                line_san=_text_tuple(raw_step, "line"),
                prompt=_text(raw_step, "prompt"),
                choices=choices,
                correct_uci=_text(raw_step, "correct"),
                explanation=_optional_text(raw_step, "explanation"),
                advance_uci=_text_tuple(raw_step, "advance"),
            )
        )
    return _DemoFlow(
        summary=DemoFlowSummary(
            id=flow_id,
            name=_text(data, "name"),
            side=_text(data, "side"),
        ),
        steps=tuple(steps),
        frontier_fen=_text(data, "frontier_fen"),
        frontier_line=_text_tuple(data, "frontier_line"),
    )


def _validate_flow(flow: _DemoFlow) -> None:
    parse_fen(flow.frontier_fen)
    for index, step in enumerate(flow.steps):
        parse_fen(step.fen)
        question = step.question
        legal_moves = set(Game(step.fen).get_moves())
        illegal = sorted(
            choice.uci for choice in question.choices if choice.uci not in legal_moves
        )
        if illegal:
            raise ValueError(f"{step.id} contains illegal choices: {illegal}")
        correct_matches = [
            choice for choice in question.choices if choice.uci == step.correct_uci
        ]
        if len(correct_matches) != 1:
            raise ValueError(
                f"{step.id} correct move must appear exactly once in choices"
            )
        if not step.advance_uci or step.advance_uci[0] != step.correct_uci:
            raise ValueError(f"{step.id} advance must begin with its correct move")

        game = Game(step.fen)
        for move in step.advance_uci:
            if move not in game.get_moves():
                raise ValueError(f"{step.id} advance contains illegal move {move!r}")
            game.apply_move(move)
        expected_fen = (
            flow.steps[index + 1].fen
            if index + 1 < len(flow.steps)
            else flow.frontier_fen
        )
        if parse_fen(game.get_fen()) != parse_fen(expected_fen):
            raise ValueError(f"{step.id} advance does not reach the next fixture FEN")


def _text(mapping: object, key: str) -> str:
    if not isinstance(mapping, dict) or not isinstance(mapping.get(key), str):
        raise TypeError(f"{key} must be a string")
    return mapping[key]


def _optional_text(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{key} must be a string or omitted")
    return value


def _text_tuple(mapping: dict[str, Any], key: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be an array of strings")
    return tuple(value)
