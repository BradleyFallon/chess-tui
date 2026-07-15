from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import shutil
from typing import Any

from fastapi.testclient import TestClient

from chess_tui.engine import EngineProcessError, FixtureEngineService
from chess_tui.flow import FlowStore
from chess_tui.web.app import WebAppSettings, create_app

FIXTURE = Path(__file__).parent / "fixtures" / "london-flow.toml"


@contextmanager
def web_client(
    tmp_path: Path, *, engine=None, frontend_dist: Path | None = None
) -> Iterator[tuple[TestClient, Path]]:
    flow_dir = tmp_path / "flows"
    flow_dir.mkdir(parents=True, exist_ok=True)
    path = flow_dir / "london.toml"
    shutil.copy2(FIXTURE, path)
    settings = WebAppSettings(
        project_root=tmp_path,
        allowed_flow_directory=flow_dir,
        startup_flow_path=path,
        frontend_dist=frontend_dist or tmp_path / "missing-dist",
    )
    with TestClient(create_app(settings, analysis_engine=engine)) as client:
        yield client, path


def session(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/sessions", json={})
    assert response.status_code == 200
    return response.json()


def move(client: TestClient, session_id: str, uci: str) -> dict[str, Any]:
    response = client.post(f"/api/sessions/{session_id}/moves", json={"uci": uci})
    assert response.status_code == 200
    return response.json()


def test_health_and_initial_v2_snapshot(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, _):
        assert client.get("/api/health").json()["engine"]["status"] == "off"
        snapshot = session(client)
        assert snapshot["phase"] == "policy-ready"
        assert snapshot["flow"]["policyModel"] == "deterministic-v2"
        assert snapshot["flow"]["side"] == "white"
        assert snapshot["decision"]["sourceId"] == "develop-d-pawn"
        assert snapshot["decision"]["moveUci"] == "d2d4"
        assert snapshot["rules"]["selected"]["id"] == "develop-d-pawn"
        assert snapshot["rules"]["dormant"]
        assert all(
            item["kind"] != "opponent-reply" for item in snapshot["rules"]["overrides"]
        )


def test_correct_move_auto_advances_and_opponent_move_returns_policy(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        result = move(client, created["sessionId"], "d2d4")
        assert result["phase"] == "opponent-ready"
        assert result["attempt"] is None
        assert result["activity"][-1]["title"] == "White played d4"
        result = move(client, created["sessionId"], "d7d5")
        assert result["phase"] == "policy-ready"
        assert result["decision"]["moveSan"] == "Bf4"
        assert result["position"]["historySan"] == ["d4", "d5"]


def test_mismatch_retry_and_continue_selected_move(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        mismatch = move(client, session_id, "e2e4")
        assert mismatch["phase"] == "policy-result"
        assert mismatch["attempt"]["result"] == "mismatch"
        assert mismatch["attempt"]["expectedSan"] == "d4"
        retried = client.post(
            f"/api/sessions/{session_id}/policy/retry", json={}
        ).json()
        assert retried["phase"] == "policy-ready"
        move(client, session_id, "e2e4")
        continued = client.post(
            f"/api/sessions/{session_id}/policy/continue", json={}
        ).json()
        assert continued["phase"] == "opponent-ready"
        assert continued["position"]["historySan"] == ["d4"]


def test_engine_review_and_next_opponent(tmp_path: Path) -> None:
    with web_client(tmp_path, engine=FixtureEngineService()) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        mismatch = move(client, session_id, "e2e4")
        assert mismatch["attempt"]["engineReview"]["status"] == "ready"
        client.post(f"/api/sessions/{session_id}/policy/retry", json={})
        move(client, session_id, "d2d4")
        response = client.post(f"/api/sessions/{session_id}/opponent/next", json={})
        assert response.status_code == 200
        assert response.json()["phase"] == "policy-ready"


def test_position_analysis_returns_book_and_engine_candidates(tmp_path: Path) -> None:
    class CountingEngine(FixtureEngineService):
        def __init__(self) -> None:
            super().__init__()
            self.analysis_counts: list[int] = []

        async def analyse(self, board, *, count=4):
            self.analysis_counts.append(count)
            return await super().analyse(board, count=count)

    engine = CountingEngine()
    with web_client(tmp_path, engine=engine) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        move(client, session_id, "d2d4")
        response = client.post(f"/api/sessions/{session_id}/analysis", json={})

        assert response.status_code == 200
        snapshot = response.json()
        assert snapshot["phase"] == "opponent-ready"
        assert snapshot["position"]["historySan"] == ["d4"]
        activity = snapshot["activity"][-1]
        assert activity["title"] == "Position analysis"
        analysis = activity["analysis"]
        assert analysis["bookMoves"][0] == {
            "uci": "d7d5",
            "san": "d5",
            "source": "local-book",
            "games": 800_000,
            "frequency": 0.46,
        }
        assert len(analysis["engineMoves"]) == 4
        assert all(row["principalVariation"] for row in analysis["engineMoves"])

        client.post(f"/api/sessions/{session_id}/analysis", json={})
        assert engine.analysis_counts.count(4) == 1


def test_position_analysis_includes_policy_move_and_requires_engine(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path, engine=FixtureEngineService()) as (client, _):
        created = session(client)
        response = client.post(
            f"/api/sessions/{created['sessionId']}/analysis", json={}
        )
        book_moves = response.json()["activity"][-1]["analysis"]["bookMoves"]
        assert book_moves == [
            {
                "uci": "d2d4",
                "san": "d4",
                "source": "policy",
                "games": None,
                "frequency": None,
            }
        ]

    with web_client(tmp_path) as (client, _):
        created = session(client)
        response = client.post(
            f"/api/sessions/{created['sessionId']}/analysis", json={}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "ENGINE_ERROR"
        unchanged = client.get(f"/api/sessions/{created['sessionId']}").json()
        assert len(unchanged["activity"]) == 1


def test_engine_failure_returns_valid_snapshot_with_visible_error(
    tmp_path: Path,
) -> None:
    class FailingEngine(FixtureEngineService):
        async def analyse(self, board, *, count=4):
            raise EngineProcessError("engine stopped")

    with web_client(tmp_path, engine=FailingEngine()) as (client, _):
        snapshot = session(client)
        assert snapshot["phase"] == "policy-ready"
        assert snapshot["evaluation"]["status"] == "error"
        assert snapshot["errors"][0]["code"] == "ENGINE_ERROR"
        mismatch = move(client, snapshot["sessionId"], "e2e4")
        assert mismatch["attempt"]["engineReview"]["status"] == "error"


def test_exact_override_precedes_rules(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        move(client, session_id, "d2d4")
        result = move(client, session_id, "e7e5")
        assert result["decision"]["source"] == "exact-override"
        assert result["decision"]["moveSan"] == "dxe5"
        assert result["rules"]["selected"]["kind"] == "exact-override"


def test_rule_edit_is_atomic_and_reassesses_pending_attempt(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, path):
        created = session(client)
        session_id = created["sessionId"]
        move(client, session_id, "e2e4")
        payload = {
            "priority": 400,
            "enabled": True,
            "note": "Claim with e4.",
            "move": {"piece": "white:e2", "to": "e4"},
            "activateWhen": None,
            "retireWhen": {"moved": "white:e2"},
        }
        response = client.put(
            f"/api/sessions/{session_id}/rules/develop-d-pawn", json=payload
        )
        assert response.status_code == 200
        assert response.json()["phase"] == "opponent-ready"
        assert response.json()["position"]["historySan"] == ["e4"]
        assert FlowStore().load(path).rules[0].move.to_square == "e4"

        original = path.read_text(encoding="utf-8")
        payload["priority"] = 390
        failed = client.put(
            f"/api/sessions/{session_id}/rules/develop-d-pawn", json=payload
        )
        assert failed.status_code == 422
        assert path.read_text(encoding="utf-8") == original


def test_override_edit_and_validation(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, path):
        created = session(client)
        session_id = created["sessionId"]
        payload = {
            "afterSan": ["d4", "e5"],
            "enabled": False,
            "note": "Temporarily disabled",
            "move": {"piece": "white:d2", "to": "e5"},
        }
        response = client.put(
            f"/api/sessions/{session_id}/overrides/after-d4-e5", json=payload
        )
        assert response.status_code == 200
        assert not FlowStore().load(path).overrides[0].enabled
        payload["afterSan"] = ["illegal"]
        failed = client.put(
            f"/api/sessions/{session_id}/overrides/after-d4-e5", json=payload
        )
        assert failed.status_code == 422
        assert not FlowStore().load(path).overrides[0].enabled


def test_back_restart_source_and_structured_errors(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        source = client.get(f"/api/sessions/{session_id}/flow/source")
        assert source.status_code == 200 and "[[rules]]" in source.json()["content"]
        move(client, session_id, "d2d4")
        back = client.post(f"/api/sessions/{session_id}/back", json={}).json()
        assert back["position"]["historySan"] == []
        restarted = client.post(f"/api/sessions/{session_id}/restart", json={}).json()
        assert restarted["phase"] == "policy-ready"
        missing = client.get("/api/sessions/missing")
        assert (
            missing.status_code == 404
            and missing.json()["error"]["code"] == "SESSION_NOT_FOUND"
        )
        invalid = client.post(f"/api/sessions/{session_id}/moves", json={"uci": "x"})
        assert (
            invalid.status_code == 422
            and invalid.json()["error"]["code"] == "INVALID_REQUEST"
        )


def test_flow_path_restriction_and_static_fallback(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, _):
        response = client.post("/api/sessions", json={"flowPath": "../private.toml"})
        assert response.status_code == 400
        page = client.get("/develop")
        assert page.status_code == 503 and "web build not found" in page.text

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<main>built app</main>", encoding="utf-8")
    with web_client(tmp_path / "built", frontend_dist=dist) as (client, _):
        assert "built app" in client.get("/develop").text
