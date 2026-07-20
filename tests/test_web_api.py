from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

from chess_tui.web.app import WebAppSettings, create_app


@pytest.fixture
def web_client(tmp_path: Path):
    flows = tmp_path / "flows"
    flows.mkdir()
    london = flows / "london.toml"
    shutil.copy2("flows/london.toml", london)
    settings = WebAppSettings(
        project_root=tmp_path,
        allowed_flow_directory=flows,
        startup_flow_path=london,
        frontend_dist=tmp_path / "dist",
    )
    with TestClient(create_app(settings)) as client:
        yield client, london


def create_session(client: TestClient) -> dict:
    response = client.post("/api/sessions")
    assert response.status_code == 200
    return response.json()


def test_snapshot_returns_piece_scripts_opponents_relations_and_v4_decision(
    web_client,
) -> None:
    client, _ = web_client
    snapshot = create_session(client)
    assert snapshot["rulebook"]["version"] == 4
    assert snapshot["decision"]["instructionRef"] == "d-pawn.develop"
    assert snapshot["decision"]["moveSan"] == "d4"
    pieces = {item["alias"]: item for item in snapshot["pieceScripts"]}
    assert pieces["d-pawn"]["authorable"] is True
    assert pieces["black-queenside-bishop"]["authorable"] is False
    assert "defendersByAttacker" in pieces["d-pawn"]["relationships"]
    assert snapshot["developmentOrder"][0] == "d-pawn"
    assert "d-pawn.accept-englund" in snapshot["interruptOrder"]


def test_development_preview_apply_delete_and_reorder(web_client) -> None:
    client, path = web_client
    snapshot = create_session(client)
    session_id = snapshot["sessionId"]
    payload = {
        "alias": "queen",
        "to": "a4",
        "requires": ["c-pawn.develop"],
        "when": None,
        "why": "Use a restrained center.",
    }
    before = path.read_text()
    preview = client.post(
        f"/api/sessions/{session_id}/development/validate", json=payload
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is True
    assert path.read_text() == before
    applied = client.post(f"/api/sessions/{session_id}/development", json=payload)
    assert applied.status_code == 200
    piece = next(
        item for item in applied.json()["pieceScripts"] if item["alias"] == "queen"
    )
    assert piece["development"]["to"] == "a4"
    reordered_aliases = list(reversed(applied.json()["developmentOrder"]))
    reordered = client.put(
        f"/api/sessions/{session_id}/orders/development",
        json={"aliases": reordered_aliases},
    )
    assert reordered.status_code == 200
    assert reordered.json()["developmentOrder"] == reordered_aliases
    deleted = client.delete(f"/api/sessions/{session_id}/development/queen")
    assert deleted.status_code == 200
    assert "queen" not in deleted.json()["developmentOrder"]


def test_interrupt_wizard_contract_attempt_order_required_and_conditions(
    web_client,
) -> None:
    client, _ = web_client
    session_id = create_session(client)["sessionId"]
    payload = {
        "alias": "queenside-knight",
        "id": "new-pressure",
        "requires": [],
        "afterSan": None,
        "when": {"under_defended": "self"},
        "required": True,
        "attempts": [
            {"capture": "attacker"},
            {"captureType": "bishop"},
            {"move": "e2"},
        ],
        "why": "Resolve pressure deterministically.",
    }
    preview = client.post(
        f"/api/sessions/{session_id}/interrupts/validate", json=payload
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is True
    applied = client.post(f"/api/sessions/{session_id}/interrupts", json=payload)
    assert applied.status_code == 200
    knight = next(
        item
        for item in applied.json()["pieceScripts"]
        if item["alias"] == "queenside-knight"
    )
    rule = next(item for item in knight["interrupts"] if item["id"] == "new-pressure")
    assert rule["required"] is True
    assert [item["kind"] for item in rule["attempts"]] == [
        "capture-attacker",
        "capture-type",
        "move",
    ]
    assert rule["when"] == {"under_defended": "self"}
    reordered_refs = [
        "queenside-knight.new-pressure",
        *(
            reference
            for reference in applied.json()["interruptOrder"]
            if reference != "queenside-knight.new-pressure"
        ),
    ]
    reordered = client.put(
        f"/api/sessions/{session_id}/orders/interrupts",
        json={"ruleRefs": reordered_refs},
    )
    assert reordered.status_code == 200
    assert reordered.json()["interruptOrder"] == reordered_refs
    deleted = client.delete(
        f"/api/sessions/{session_id}/interrupts/queenside-knight/new-pressure"
    )
    assert deleted.status_code == 200


def test_invalid_preview_does_not_modify_rulebook_or_backup(web_client) -> None:
    client, path = web_client
    session_id = create_session(client)["sessionId"]
    before = path.read_text()
    backup = path.with_suffix(".toml.bak")
    preview = client.post(
        f"/api/sessions/{session_id}/interrupts/validate",
        json={
            "alias": "d-pawn",
            "id": "bad",
            "requires": ["missing.develop"],
            "afterSan": None,
            "when": None,
            "required": False,
            "attempts": [{"move": "d5"}],
            "why": "Invalid dependency.",
        },
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is False
    assert path.read_text() == before
    assert not backup.exists()


def test_unknown_piece_alias_is_a_validation_error(web_client) -> None:
    client, _ = web_client
    session_id = create_session(client)["sessionId"]
    payload = {
        "alias": "missing-piece",
        "to": "e4",
        "requires": [],
        "when": None,
        "why": "This alias is invalid.",
    }
    preview = client.post(
        f"/api/sessions/{session_id}/development/validate",
        json=payload,
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is False
    applied = client.post(
        f"/api/sessions/{session_id}/development",
        json=payload,
    )
    assert applied.status_code == 422
    assert applied.json()["error"]["code"] == "FLOW_VALIDATION_ERROR"


def test_accept_here_persists_exact_interrupt_and_commits_attempt(web_client) -> None:
    client, path = web_client
    snapshot = create_session(client)
    session_id = snapshot["sessionId"]
    mismatch = client.post(f"/api/sessions/{session_id}/moves", json={"uci": "e2e4"})
    assert mismatch.json()["attempt"]["result"] == "mismatch"
    accepted = client.post(f"/api/sessions/{session_id}/attempt/accept-here")
    assert accepted.status_code == 200
    assert accepted.json()["position"]["historySan"] == ["e4"]
    source = path.read_text()
    assert "after = []" in source
    assert 'why = "Accepted e4 in this exact position."' in source
    assert "[[overrides]]" not in source


def test_typed_frontier_snapshot_and_black_controlled_rulebook(tmp_path: Path) -> None:
    flows = tmp_path / "flows"
    flows.mkdir()
    path = flows / "black.toml"
    path.write_text("""
version = 4
name = "Black Rulebook"
start_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1"
side = "black"
development_order = ["d-pawn"]
interrupt_order = []

[pieces.d-pawn]
ref = "piece:black:pawn:d"

[pieces.d-pawn.develop]
to = "d5"
why = "Claim the center."

[pieces.white-d-pawn]
ref = "piece:white:pawn:d"
""".strip() + "\n")
    settings = WebAppSettings(
        project_root=tmp_path,
        allowed_flow_directory=flows,
        startup_flow_path=path,
        frontend_dist=tmp_path / "dist",
    )
    with TestClient(create_app(settings)) as client:
        snapshot = create_session(client)
    assert snapshot["rulebook"]["side"] == "black"
    assert snapshot["decision"]["moveSan"] == "d5"
    white = next(
        item for item in snapshot["pieceScripts"] if item["alias"] == "white-d-pawn"
    )
    assert white["authorable"] is False
