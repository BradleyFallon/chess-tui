from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import shutil

import chess
from fastapi.testclient import TestClient

from chess_tui import DEFAULT_STARTING_FEN
from chess_tui.engine import (
    AnalysedMove,
    EngineProcessError,
    EngineProfile,
    FixtureEngineService,
)
from chess_tui.flow import DefaultRule, FlowStore, WhiteFlow
from chess_tui.web.app import WebAppSettings, create_app

PROJECT_ROOT = Path(__file__).parents[1]
LONDON_FLOW = PROJECT_ROOT / "tests" / "fixtures" / "london-flow.toml"


@contextmanager
def _web_client(
    tmp_path: Path,
    *,
    engine=None,
    frontend_dist: Path | None = None,
) -> Iterator[tuple[TestClient, Path]]:
    flow_directory = tmp_path / "flows"
    flow_directory.mkdir(exist_ok=True)
    flow_path = flow_directory / "london.toml"
    shutil.copy2(LONDON_FLOW, flow_path)
    settings = WebAppSettings(
        project_root=tmp_path,
        allowed_flow_directory=flow_directory,
        startup_flow_path=flow_path,
        frontend_dist=frontend_dist or tmp_path / "missing-dist",
    )
    with TestClient(create_app(settings, analysis_engine=engine)) as client:
        yield client, flow_path


def _create_session(client: TestClient) -> dict:
    response = client.post("/api/sessions", json={})
    assert response.status_code == 200
    return response.json()


def _move(client: TestClient, session_id: str, uci: str) -> dict:
    response = client.post(
        f"/api/sessions/{session_id}/moves",
        json={"uci": uci},
    )
    assert response.status_code == 200
    return response.json()


def test_web_health_and_initial_legacy_snapshot(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, _):
        assert client.get("/api/health").json() == {
            "status": "ok",
            "engine": {"status": "off"},
        }

        snapshot = _create_session(client)

        assert snapshot["mode"] == "develop"
        assert snapshot["phase"] == "white-ready"
        assert snapshot["flow"] == {
            "name": "London System",
            "version": 1,
            "path": "flows/london.toml",
            "policyModel": "legacy-v1",
        }
        assert snapshot["position"]["historySan"] == []
        assert snapshot["position"]["fen"] == DEFAULT_STARTING_FEN
        assert snapshot["decision"]["moveUci"] == "d2d4"
        assert snapshot["decision"]["source"] == "default"
        assert snapshot["evaluation"]["status"] == "engine-off"
        assert "lifecycle rules are not available" in snapshot["rules"]["modelMessage"]
        assert snapshot["activity"][-1]["title"] == "Development session ready"


def test_web_rejects_flow_outside_allowed_directory(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, _):
        response = client.post(
            "/api/sessions",
            json={"flowPath": "../private.toml"},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_web_rejects_missing_flow_inside_allowed_directory(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, _):
        response = client.post(
            "/api/sessions",
            json={"flowPath": "flows/missing.toml"},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FLOW_VALIDATION_ERROR"


def test_web_correct_white_continue_and_black_move(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, _):
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]

        result = _move(client, session_id, "d2d4")
        assert result["phase"] == "white-result"
        assert result["attempt"]["result"] == "correct"
        assert result["position"]["historySan"] == ["d4"]
        assert result["position"]["legalMovesUci"] == []
        assert result["activity"][-1] == {
            "id": 2,
            "kind": "success",
            "title": "White played d4",
            "message": "Correct. Control the center.",
        }

        continued = client.post(f"/api/sessions/{session_id}/white/continue").json()
        assert continued["phase"] == "black-ready"
        assert "d7d5" in continued["position"]["legalMovesUci"]

        next_turn = _move(client, session_id, "d7d5")
        assert next_turn["phase"] == "white-ready"
        assert next_turn["position"]["historySan"] == ["d4", "d5"]
        assert next_turn["decision"]["moveSan"] == "Bf4"
        assert next_turn["position"]["lastMoveUci"] == "d7d5"
        assert next_turn["activity"][-1]["title"] == "Black played d5"
        refreshed = client.get(f"/api/sessions/{session_id}").json()
        assert refreshed["activity"] == next_turn["activity"]


def test_web_white_mismatch_retry_and_keep(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, _):
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]

        mismatch = _move(client, session_id, "e2e4")
        assert mismatch["attempt"]["result"] == "mismatch-default"
        assert mismatch["attempt"]["playedSan"] == "e4"
        assert mismatch["attempt"]["expectedSan"] == "d4"
        assert mismatch["activity"][-1]["kind"] == "warning"
        assert "expects d4" in mismatch["activity"][-1]["message"]

        retried = client.post(f"/api/sessions/{session_id}/white/retry").json()
        assert retried["phase"] == "white-ready"
        assert retried["position"]["historySan"] == []
        assert retried["activity"][-1]["title"] == "Retry White’s move"

        _move(client, session_id, "e2e4")
        kept = client.post(f"/api/sessions/{session_id}/white/keep").json()
        assert kept["phase"] == "black-ready"
        assert kept["position"]["historySan"] == ["d4"]


def test_web_next_plays_an_engine_move_for_black(tmp_path: Path) -> None:
    engine = FixtureEngineService(session_seed="black-next")
    with _web_client(tmp_path, engine=engine) as (client, _):
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]
        _move(client, session_id, "d2d4")
        ready = client.post(f"/api/sessions/{session_id}/white/continue").json()
        assert ready["phase"] == "black-ready"

        response = client.post(f"/api/sessions/{session_id}/black/next")

        assert response.status_code == 200
        advanced = response.json()
        assert advanced["phase"] == "white-ready"
        assert len(advanced["position"]["historySan"]) == 2
        assert advanced["activity"][-1]["title"].startswith("Black played ")
        assert "engine selected" in advanced["activity"][-1]["message"]


def test_web_next_requires_an_engine_and_preserves_black_turn(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, _):
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]
        _move(client, session_id, "d2d4")
        client.post(f"/api/sessions/{session_id}/white/continue")

        response = client.post(f"/api/sessions/{session_id}/black/next")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "ENGINE_ERROR"
        current = client.get(f"/api/sessions/{session_id}").json()
        assert current["phase"] == "black-ready"
        assert current["position"]["historySan"] == ["d4"]


def test_web_frontier_is_read_only_and_retryable(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, flow_path):
        FlowStore().save(
            flow_path,
            WhiteFlow(1, "Frontier", DEFAULT_STARTING_FEN, (), ()),
        )
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]
        assert snapshot["decision"]["status"] == "frontier"

        frontier = _move(client, session_id, "d2d4")
        assert frontier["attempt"]["result"] == "frontier"
        assert frontier["attempt"]["expectedSan"] is None

        restored = client.post(f"/api/sessions/{session_id}/white/retry").json()
        assert restored["position"]["historySan"] == []
        assert restored["decision"]["status"] == "frontier"


def test_web_illegal_move_is_structured_and_preserves_session(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, _):
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]

        response = client.post(
            f"/api/sessions/{session_id}/moves",
            json={"uci": "e2e5"},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_MOVE"

        current = client.get(f"/api/sessions/{session_id}").json()
        assert current["position"]["historySan"] == []
        assert current["position"]["fen"] == snapshot["position"]["fen"]


def test_web_back_and_restart_return_complete_snapshots(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, _):
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]
        _move(client, session_id, "d2d4")
        client.post(f"/api/sessions/{session_id}/white/continue")
        _move(client, session_id, "d7d5")

        backed = client.post(f"/api/sessions/{session_id}/back").json()
        assert backed["position"]["historySan"] == []
        assert backed["decision"]["moveSan"] == "d4"
        assert backed["navigation"]["canBack"] is False

        _move(client, session_id, "d2d4")
        restarted = client.post(f"/api/sessions/{session_id}/restart").json()
        assert restarted["position"]["historySan"] == []
        assert restarted["navigation"] == {"canBack": False, "canRestart": False}


def test_web_navigation_and_session_errors_are_structured(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, _):
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]

        back = client.post(f"/api/sessions/{session_id}/back")
        assert back.status_code == 400
        assert back.json()["error"]["code"] == "INVALID_NAVIGATION"

        missing = client.get("/api/sessions/not-a-session")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "SESSION_NOT_FOUND"

        invalid = client.post("/api/sessions", json={"unknown": True})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_REQUEST"


def test_web_fixture_evaluation_and_mismatch_review_are_white_normalized(
    tmp_path: Path,
) -> None:
    engine = FixtureEngineService(session_seed="web")
    with _web_client(tmp_path, engine=engine) as (client, _):
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]
        assert snapshot["evaluation"]["status"] == "ready"
        assert snapshot["evaluation"]["centipawns"] == 0

        mismatch = _move(client, session_id, "e2e4")
        review = mismatch["attempt"]["engineReview"]
        assert review["status"] == "ready"
        assert review["bestMoveUci"] is not None
        assert review["evaluationBeforeCp"] == 0
        assert mismatch["evaluation"]["previousCentipawns"] == 0

    assert engine.closed


def test_web_evaluation_cache_reuses_position_analysis(tmp_path: Path) -> None:
    class CountingEngine(FixtureEngineService):
        def __init__(self) -> None:
            super().__init__(session_seed="count")
            self.analysis_requests = 0

        async def analyse(
            self, board: chess.Board, *, count: int = 4
        ) -> tuple[AnalysedMove, ...]:
            self.analysis_requests += 1
            return await super().analyse(board, count=count)

    engine = CountingEngine()
    with _web_client(tmp_path, engine=engine) as (client, _):
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]
        client.get(f"/api/sessions/{session_id}")
        assert engine.analysis_requests == 1

        _move(client, session_id, "e2e4")
        assert engine.analysis_requests == 2


def test_web_engine_error_remains_in_valid_workspace(tmp_path: Path) -> None:
    class FailingEngine:
        async def choose_move(
            self, board: chess.Board, profile: EngineProfile
        ) -> chess.Move:
            return next(iter(board.legal_moves))

        async def analyse(
            self, board: chess.Board, *, count: int = 4
        ) -> tuple[AnalysedMove, ...]:
            raise EngineProcessError("engine unavailable")

        async def close(self) -> None:
            return None

    with _web_client(tmp_path, engine=FailingEngine()) as (client, _):
        snapshot = _create_session(client)

        assert snapshot["phase"] == "white-ready"
        assert snapshot["evaluation"]["status"] == "error"
        assert snapshot["errors"][0]["code"] == "ENGINE_ERROR"
        assert client.get("/api/health").json()["engine"]["status"] == "error"


def test_web_game_over_snapshot_and_restart(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, flow_path):
        FlowStore().save(
            flow_path,
            WhiteFlow(
                1,
                "Mate",
                "7k/8/5KQ1/8/8/8/8/8 w - - 0 1",
                (DefaultRule(1, "Qg7#"),),
                (),
            ),
        )
        snapshot = _create_session(client)
        session_id = snapshot["sessionId"]

        ended = _move(client, session_id, "g6g7")
        assert ended["phase"] == "game-over"
        assert ended["position"]["gameOver"] == {
            "result": "1-0",
            "termination": "checkmate",
            "winner": "white",
        }
        assert ended["evaluation"]["status"] == "game-over"

        restarted = client.post(f"/api/sessions/{session_id}/restart").json()
        assert restarted["phase"] == "white-ready"


def test_web_static_assets_and_spa_fallback(tmp_path: Path) -> None:
    dist = tmp_path / "web-dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<main>Chess Flow</main>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("export {};", encoding="utf-8")

    with _web_client(tmp_path, frontend_dist=dist) as (client, _):
        assert client.get("/").text == "<main>Chess Flow</main>"
        assert client.get("/develop").text == "<main>Chess Flow</main>"
        assert client.get("/assets/app.js").text == "export {};"


def test_web_missing_build_keeps_api_available(tmp_path: Path) -> None:
    with _web_client(tmp_path) as (client, _):
        frontend = client.get("/")
        assert frontend.status_code == 503
        assert "npm run build" in frontend.text
        assert client.get("/api/health").status_code == 200
