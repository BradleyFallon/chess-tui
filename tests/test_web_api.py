from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import shutil
from typing import Any

from fastapi.testclient import TestClient

from chess_tui.engine import EngineProcessError, FixtureEngineService
from chess_tui.flow import DevelopmentAssignment, FlowStore
from chess_tui.web.app import WebAppSettings, create_app

FIXTURE = Path(__file__).parents[1] / "flows" / "london.toml"


@contextmanager
def web_client(
    tmp_path: Path, *, engine=None, frontend_dist: Path | None = None
) -> Iterator[tuple[TestClient, Path]]:
    flow_dir = tmp_path / "flows"
    flow_dir.mkdir(parents=True, exist_ok=True)
    path = flow_dir / "london.toml"
    shutil.copy2(FIXTURE, path)
    store = FlowStore()
    store.save(path, replace(store.load(path), opening_tags=()))
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


def test_health_and_initial_v3_snapshot(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, _):
        assert client.get("/api/health").json()["engine"]["status"] == "off"
        snapshot = session(client)
        assert snapshot["phase"] == "policy-ready"
        assert snapshot["flow"]["policyModel"] == "deterministic-v3"
        assert snapshot["flow"]["side"] == "white"
        assert snapshot["decision"]["sourceId"] == "develop-d-pawn"
        assert snapshot["decision"]["moveUci"] == "d2d4"
        assert snapshot["rules"]["selected"]["id"] == "develop-d-pawn"
        assert snapshot["rules"]["development"]
        assert snapshot["rules"]["structures"]
        assert snapshot["opening"]["primaryMatch"] is None
        assert snapshot["openingHistory"] == []
        assert all(
            item["kind"] != "opponent-reply" for item in snapshot["rules"]["overrides"]
        )
        command_ids = {item["id"] for item in snapshot["availableCommands"]}
        assert "play_move" in command_ids
        assert "hint_policy_move" in command_ids
        assert "analyse_position" not in command_ids
        assert {
            "inspect_opening",
            "list_openings",
            "list_defenses",
            "inspect_book",
            "inspect_book_history",
        } <= command_ids
        assert "restart" not in command_ids


def test_starting_piece_snapshots_and_development_draft_operations(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path) as (client, path):
        created = session(client)
        session_id = created["sessionId"]
        pieces = {item["ref"]: item for item in created["startingPieces"]}
        d_pawn = pieces["piece:white:pawn:d"]
        assert d_pawn["state"] == "undeveloped"
        assert d_pawn["currentSquare"] == "d2"
        assert d_pawn["developmentRules"][0]["status"] == "selected"
        assert d_pawn["developmentRules"][0]["order"] == 1

        draft = {
            "id": None,
            "piece": "piece:white:pawn:a",
            "target": "a3",
            "structures": [],
            "note": "Give the rook luft.",
            "readyWhen": {"moved": "piece:white:pawn:d"},
        }
        validation = client.post(
            f"/api/sessions/{session_id}/development-rules/validate",
            json=draft,
        )
        assert validation.status_code == 200
        assert validation.json()["valid"]
        assert "piece:white:pawn:a" not in path.read_text(encoding="utf-8")

        applied = client.post(
            f"/api/sessions/{session_id}/development-rules", json=draft
        )
        assert applied.status_code == 200
        a_pawn = next(
            item
            for item in applied.json()["startingPieces"]
            if item["ref"] == "piece:white:pawn:a"
        )
        assert a_pawn["developmentRules"][0]["target"] == "a3"

        development_ids = [
            rule["id"]
            for item in applied.json()["startingPieces"]
            for rule in item["developmentRules"]
        ]
        reordered = client.put(
            f"/api/sessions/{session_id}/development-rules/order",
            json={"ruleIds": list(reversed(development_ids))},
        )
        assert reordered.status_code == 200
        orders = sorted(
            (
                rule["order"],
                rule["id"],
            )
            for item in reordered.json()["startingPieces"]
            for rule in item["developmentRules"]
        )
        assert [item[1] for item in orders] == list(reversed(development_ids))

        deleted = client.delete(
            f"/api/sessions/{session_id}/development-rules/develop-white-pawn-a"
        )
        assert deleted.status_code == 200
        a_pawn = next(
            item
            for item in deleted.json()["startingPieces"]
            if item["ref"] == "piece:white:pawn:a"
        )
        assert a_pawn["developmentRules"] == []


def test_invalid_development_preview_and_apply_preserve_valid_state(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path) as (client, path):
        created = session(client)
        session_id = created["sessionId"]
        original = path.read_text(encoding="utf-8")
        invalid = {
            "id": None,
            "piece": "piece:white:pawn:queenside",
            "target": "z9",
            "structures": [],
            "readyWhen": None,
        }
        preview = client.post(
            f"/api/sessions/{session_id}/development-rules/validate",
            json=invalid,
        )
        assert preview.status_code == 200
        assert not preview.json()["valid"]
        assert path.read_text(encoding="utf-8") == original

        applied = client.post(
            f"/api/sessions/{session_id}/development-rules", json=invalid
        )
        assert applied.status_code == 422
        assert path.read_text(encoding="utf-8") == original

        generic_edit = client.put(
            f"/api/sessions/{session_id}/rules/develop-d-pawn",
            json={
                "move": {"piece": "piece:white:pawn:d", "to": "d3"},
                "structures": [],
                "unlockWhen": None,
                "when": None,
                "expireWhen": None,
            },
        )
        assert generic_edit.status_code == 400
        assert path.read_text(encoding="utf-8") == original


def test_typed_commands_drive_moves_hints_and_phase_availability(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path, engine=FixtureEngineService()) as (client, _):
        created = session(client)
        session_id = created["sessionId"]

        hint = client.post(
            f"/api/sessions/{session_id}/commands",
            json={"command": "hint_policy_move", "source": "ui"},
        )
        assert hint.status_code == 200
        assert hint.json()["effects"] == [{"kind": "highlight-move", "uci": "d2d4"}]
        assert hint.json()["workspace"]["chat"] == []

        played = client.post(
            f"/api/sessions/{session_id}/commands",
            json={
                "command": "play_move",
                "source": "ui",
                "notation": "uci",
                "move": "d2d4",
            },
        )
        assert played.status_code == 200
        workspace = played.json()["workspace"]
        assert workspace["phase"] == "opponent-ready"
        command_ids = {item["id"] for item in workspace["availableCommands"]}
        assert {"next_opponent", "play_move", "go_back", "restart"} <= command_ids
        assert "hint_policy_move" not in command_ids
        assert "explain_decision" not in command_ids


def test_opening_snapshots_timeline_and_read_only_command_attachments(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        session_id = created["sessionId"]

        played = move(client, session_id, "d2d4")
        assert played["opening"]["primaryMatch"]["name"] == "Queen's Pawn Game"
        assert played["opening"]["moveSource"] == "book-and-policy"
        assert played["opening"]["policyRuleId"] == "develop-d-pawn"
        opening_event = played["activity"][-1]["attachment"]
        assert played["activity"][-1]["kind"] == "commentary"
        assert played["activity"][-1]["title"] == "Opening after 1.d4"
        assert opening_event["kind"] == "opening-context"
        assert opening_event["presentation"] == "transition"
        assert opening_event["entry"]["san"] == "d4"

        command_kinds = {
            "/opening": "opening-context",
            "/openings": "opening-list",
            "/defenses": "defense-list",
            "/book": "book-details",
            "/book-history": "book-history",
        }
        for slash, kind in command_kinds.items():
            response = client.post(
                f"/api/sessions/{session_id}/chat", json={"text": slash}
            )
            assert response.status_code == 200
            attachment = response.json()["workspace"]["chat"][-1]["attachment"]
            assert attachment["kind"] == kind

        history_response = client.post(
            f"/api/sessions/{session_id}/chat", json={"text": "/book-history"}
        )
        history = history_response.json()["workspace"]["chat"][-1]["attachment"]
        assert history["entries"][0]["context"]["moveSource"] == "book-and-policy"
        assert history["entries"][0]["context"]["playedMoveInBook"] is True


def test_opening_matches_can_be_saved_as_durable_flow_labels(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path) as (client, path):
        created = session(client)
        session_id = created["sessionId"]

        after_d4 = move(client, session_id, "d2d4")
        queen_pawn = after_d4["opening"]["primaryMatch"]
        added = client.post(
            f"/api/sessions/{session_id}/opening-tags",
            json={"recordId": queen_pawn["recordId"]},
        )
        assert added.status_code == 200
        assert added.json()["flow"]["openingTags"] == [
            {
                "recordId": queen_pawn["recordId"],
                "eco": "A40",
                "name": "Queen's Pawn Game",
            }
        ]

        move(client, session_id, "d7d5")
        after_bf4 = move(client, session_id, "c1f4")
        accelerated = after_bf4["opening"]["primaryMatch"]
        added = client.post(
            f"/api/sessions/{session_id}/opening-tags",
            json={"recordId": accelerated["recordId"]},
        )
        assert added.status_code == 200
        assert [tag["name"] for tag in added.json()["flow"]["openingTags"]] == [
            "Queen's Pawn Game",
            "Queen's Pawn Game: Accelerated London System",
        ]
        assert [tag.name for tag in FlowStore().load(path).opening_tags] == [
            "Queen's Pawn Game",
            "Queen's Pawn Game: Accelerated London System",
        ]

        duplicate = client.post(
            f"/api/sessions/{session_id}/opening-tags",
            json={"recordId": accelerated["recordId"]},
        )
        assert duplicate.status_code == 422

        removed = client.delete(
            f"/api/sessions/{session_id}/opening-tags/{accelerated['recordId']}"
        )
        assert removed.status_code == 200
        assert [tag["name"] for tag in removed.json()["flow"]["openingTags"]] == [
            "Queen's Pawn Game"
        ]


def test_typed_command_validation_and_unavailability_are_structured(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        invalid = client.post(
            f"/api/sessions/{session_id}/commands",
            json={"command": "play_move", "source": "ui", "move": "d4"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_REQUEST"

        unavailable = client.post(
            f"/api/sessions/{session_id}/commands",
            json={"command": "next_opponent", "source": "ui"},
        )
        assert unavailable.status_code == 400
        assert unavailable.json()["error"]["details"]["commandCode"] == (
            "COMMAND_UNAVAILABLE"
        )


def test_chat_parses_raw_san_and_returns_conversational_errors(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        initial_fen = created["position"]["fen"]

        rejected = client.post(
            f"/api/sessions/{session_id}/chat", json={"text": "/rule missing"}
        )
        assert rejected.status_code == 200
        unchanged = rejected.json()["workspace"]
        assert unchanged["position"]["fen"] == initial_fen
        assert unchanged["position"]["historySan"] == []
        assert unchanged["chat"][-2]["role"] == "user"
        assert unchanged["chat"][-1]["role"] == "assistant"
        assert unchanged["chat"][-1]["attachment"]["kind"] == "validation-error"
        assert unchanged["chat"][-1]["attachment"]["code"] == "UNKNOWN_RULE"

        played = client.post(f"/api/sessions/{session_id}/chat", json={"text": "d4"})
        assert played.status_code == 200
        workspace = played.json()["workspace"]
        assert workspace["position"]["historySan"] == ["d4"]
        assert workspace["chat"][-1]["text"] == "d4"
        assert workspace["activity"][-1]["sequence"] > workspace["chat"][-1]["sequence"]


def test_deterministic_chat_answers_cover_decision_rules_trace_and_position(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        expected_kinds = {
            "/why": "decision-explanation",
            "/rule develop-d-pawn": "rule-details",
            "/rules": "rule-list",
            "/trace": "decision-trace",
            "/position": "position-details",
            "/help": "command-list",
        }
        for command, expected_kind in expected_kinds.items():
            response = client.post(
                f"/api/sessions/{session_id}/chat", json={"text": command}
            )
            assert response.status_code == 200
            message = response.json()["workspace"]["chat"][-1]
            assert message["role"] == "assistant"
            assert message["attachment"]["kind"] == expected_kind

        why = client.post(
            f"/api/sessions/{session_id}/chat", json={"text": "/why"}
        ).json()["workspace"]["chat"][-1]["attachment"]
        assert why["selected"]["id"] == "develop-d-pawn"
        assert "user-authored-note" in why["provenance"]

        position = client.post(
            f"/api/sessions/{session_id}/chat", json={"text": "/position"}
        ).json()["workspace"]["chat"][-1]["attachment"]
        assert position["fen"] == created["position"]["fen"]
        assert {"uci": "d2d4", "san": "d4"} in position["legalMoves"]


def test_exact_override_explanations_and_inspection(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        move(client, session_id, "d2d4")
        position = move(client, session_id, "e7e5")
        assert position["decision"]["source"] == "exact-override"

        why = client.post(
            f"/api/sessions/{session_id}/chat", json={"text": "/why"}
        ).json()["workspace"]["chat"][-1]["attachment"]
        assert why["selected"]["kind"] == "exact-override"
        assert why["selected"]["id"] == "after-d4-e5"

        details = client.post(
            f"/api/sessions/{session_id}/chat",
            json={"text": "/rule after-d4-e5"},
        ).json()["workspace"]["chat"][-1]["attachment"]
        assert details["rule"]["kind"] == "exact-override"
        assert details["rule"]["piece"] == "piece:white:pawn:d"
        assert details["rule"]["selected"] is True


def test_chat_and_activity_sequences_survive_restart_and_limit_independently(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        response = client.post(
            f"/api/sessions/{session_id}/chat", json={"text": "/position"}
        )
        assert response.status_code == 200
        for _ in range(50):
            response = client.post(
                f"/api/sessions/{session_id}/chat", json={"text": "/position"}
            )
            assert response.status_code == 200
        workspace = response.json()["workspace"]
        assert len(workspace["chat"]) == 100
        assert len(workspace["activity"]) == 1
        assert all(
            earlier["sequence"] < later["sequence"]
            for earlier, later in zip(workspace["chat"], workspace["chat"][1:])
        )

        client.post(f"/api/sessions/{session_id}/moves", json={"uci": "d2d4"})
        restarted = client.post(
            f"/api/sessions/{session_id}/commands",
            json={"command": "restart", "source": "ui"},
        )
        assert restarted.status_code == 200
        workspace = restarted.json()["workspace"]
        assert len(workspace["chat"]) == 100
        assert workspace["activity"][-1]["title"] == "Line restarted"
        assert workspace["activity"][-1]["sequence"] > workspace["chat"][-1]["sequence"]


def test_correct_move_auto_advances_and_opponent_move_returns_policy(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        result = move(client, created["sessionId"], "d2d4")
        assert result["phase"] == "opponent-ready"
        assert result["attempt"] is None
        assert result["activity"][-2]["title"] == "White played d4"
        assert result["activity"][-1]["title"] == "Opening after 1.d4"
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


def test_mismatch_can_add_an_exact_rule_from_chat_action(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, path):
        created = session(client)
        session_id = created["sessionId"]
        mismatch = move(client, session_id, "e2e4")
        assert mismatch["phase"] == "policy-result"

        response = client.post(f"/api/sessions/{session_id}/policy/add-rule", json={})

        assert response.status_code == 200
        snapshot = response.json()
        assert snapshot["phase"] == "opponent-ready"
        assert snapshot["attempt"] is None
        assert snapshot["position"]["historySan"] == ["e4"]
        assert snapshot["activity"][-2]["title"] == "Added rule allow-e2e4-ply-0"
        assert snapshot["activity"][-1]["title"] == "Opening after 1.e4"
        override = FlowStore().load(path).overrides[-1]
        assert override.id == "allow-e2e4-ply-0"
        assert str(override.move.piece) == "white:e2"
        assert override.move.to_square == "e4"


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
        assert (
            response.json()["openingHistory"][-1]["context"]["moveSource"] == "engine"
        )


def test_position_analysis_returns_book_and_engine_candidates(tmp_path: Path) -> None:
    class CountingEngine(FixtureEngineService):
        def __init__(self) -> None:
            super().__init__()
            self.analysis_counts: list[int] = []

        async def analyse(self, board, *, count=4, profile=None):
            self.analysis_counts.append(count)
            return await super().analyse(board, count=count, profile=profile)

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
        assert activity["title"] == "Position analysis completed"
        analysis = snapshot["chat"][-1]["attachment"]["analysis"]
        assert analysis["bookMoves"]
        assert all(
            item["source"] == "opening-index" and item["openingNames"]
            for item in analysis["bookMoves"]
        )
        assert all(
            "games" not in item and "frequency" not in item
            for item in analysis["bookMoves"]
        )
        assert len(analysis["engineMoves"]) == 4
        assert all(row["principalVariation"] for row in analysis["engineMoves"])

        client.post(f"/api/sessions/{session_id}/analysis", json={})
        assert engine.analysis_counts.count(4) == 1


def test_analysis_profile_is_visible_and_changes_depth(tmp_path: Path) -> None:
    class ProfileTrackingEngine(FixtureEngineService):
        def __init__(self) -> None:
            super().__init__()
            self.profile_ids: list[str] = []

        async def analyse(self, board, *, count=4, profile=None):
            assert profile is not None
            self.profile_ids.append(profile.id)
            return await super().analyse(board, count=count, profile=profile)

    engine = ProfileTrackingEngine()
    with web_client(tmp_path, engine=engine) as (client, _):
        created = session(client)
        settings = created["analysisSettings"]
        assert settings["engineName"] == "Deterministic fixture"
        assert settings["selectedProfileId"] == "analysis"
        assert settings["billingNote"] == "Local engine: no API or per-analysis fee."
        assert [item["depth"] for item in settings["profiles"]] == [10, 15, 20, 26]
        assert created["evaluation"]["analysis"]["requestedDepth"] == 20

        changed = client.put(
            f"/api/sessions/{created['sessionId']}/analysis/settings",
            json={"profileId": "deep"},
        )

        assert changed.status_code == 200
        snapshot = changed.json()
        assert snapshot["analysisSettings"]["selectedProfileId"] == "deep"
        assert snapshot["evaluation"]["analysis"]["requestedDepth"] == 26
        assert snapshot["activity"][-1]["title"] == "Analysis set to Deep"
        assert engine.profile_ids[-1] == "deep"


def test_position_analysis_includes_policy_move_and_requires_engine(
    tmp_path: Path,
) -> None:
    with web_client(tmp_path, engine=FixtureEngineService()) as (client, _):
        created = session(client)
        response = client.post(
            f"/api/sessions/{created['sessionId']}/analysis", json={}
        )
        book_moves = response.json()["chat"][-1]["attachment"]["analysis"]["bookMoves"]
        assert book_moves[0]["uci"] == "d2d4"
        assert book_moves[0]["source"] == "book-and-policy"
        assert book_moves[0]["openingNames"]

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
        async def analyse(self, board, *, count=4, profile=None):
            raise EngineProcessError("engine stopped")

    with web_client(tmp_path, engine=FailingEngine()) as (client, _):
        snapshot = session(client)
        assert snapshot["phase"] == "policy-ready"
        assert snapshot["evaluation"]["status"] == "error"
        assert snapshot["errors"][0]["code"] == "ENGINE_ERROR"
        analysis = client.post(
            f"/api/sessions/{snapshot['sessionId']}/chat", json={"text": "/analyse"}
        )
        assert analysis.status_code == 200
        analysis_workspace = analysis.json()["workspace"]
        assert analysis_workspace["chat"][-1]["attachment"]["kind"] == (
            "validation-error"
        )
        assert analysis_workspace["chat"][-1]["attachment"]["code"] == "ENGINE_ERROR"
        assert len(analysis_workspace["activity"]) == 1
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
        move(client, session_id, "d2d3")
        payload = {
            "id": "develop-d-pawn",
            "piece": "piece:white:pawn:d",
            "target": "d3",
            "structures": [],
            "note": "Claim with d3.",
            "readyWhen": None,
        }
        response = client.post(
            f"/api/sessions/{session_id}/development-rules", json=payload
        )
        assert response.status_code == 200
        assert response.json()["phase"] == "opponent-ready"
        assert response.json()["position"]["historySan"] == ["d3"]
        saved = FlowStore().load(path).development[0]
        assert isinstance(saved, DevelopmentAssignment)
        assert saved.target == "d3"

        original = path.read_text(encoding="utf-8")
        payload["target"] = "zz"
        failed = client.post(
            f"/api/sessions/{session_id}/development-rules", json=payload
        )
        assert failed.status_code == 422
        assert path.read_text(encoding="utf-8") == original


def test_override_edit_and_validation(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, path):
        created = session(client)
        session_id = created["sessionId"]
        payload = {
            "afterSan": ["d4", "e5"],
            "note": "Updated exception",
            "move": {"piece": "piece:white:pawn:d", "to": "e5"},
        }
        response = client.put(
            f"/api/sessions/{session_id}/overrides/after-d4-e5", json=payload
        )
        assert response.status_code == 200
        assert FlowStore().load(path).overrides[0].note == "Updated exception"
        payload["afterSan"] = ["illegal"]
        failed = client.put(
            f"/api/sessions/{session_id}/overrides/after-d4-e5", json=payload
        )
        assert failed.status_code == 422
        assert FlowStore().load(path).overrides[0].note == "Updated exception"


def test_structure_edit_and_authored_policy_reordering(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, path):
        created = session(client)
        session_id = created["sessionId"]

        response_ids = [item["id"] for item in created["rules"]["responses"]]
        reordered = client.put(
            f"/api/sessions/{session_id}/policy-order/response",
            json={"itemIds": list(reversed(response_ids))},
        )
        assert reordered.status_code == 200
        assert [item.id for item in FlowStore().load(path).responses] == list(
            reversed(response_ids)
        )

        traditional = next(
            item
            for item in reordered.json()["rules"]["structures"]
            if item["id"] == "traditional"
        )
        updated = client.put(
            f"/api/sessions/{session_id}/structures/traditional",
            json={
                "name": "Traditional London shell",
                "note": "Updated from Development Mode.",
                "availableWhen": traditional["availableWhen"]["expression"],
                "selectedWhen": traditional["selectedWhen"]["expression"],
            },
        )
        assert updated.status_code == 200
        saved = FlowStore().load(path)
        assert (
            next(item.name for item in saved.structures if item.id == "traditional")
            == "Traditional London shell"
        )

        structure_ids = [item.id for item in saved.structures]
        order = client.put(
            f"/api/sessions/{session_id}/structures/order",
            json={"structureIds": list(reversed(structure_ids))},
        )
        assert order.status_code == 200
        assert [item.id for item in FlowStore().load(path).structures] == list(
            reversed(structure_ids)
        )


def test_back_restart_source_and_structured_errors(tmp_path: Path) -> None:
    with web_client(tmp_path) as (client, _):
        created = session(client)
        session_id = created["sessionId"]
        source = client.get(f"/api/sessions/{session_id}/flow/source")
        assert (
            source.status_code == 200 and "[[development]]" in source.json()["content"]
        )
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
