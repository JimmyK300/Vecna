import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aic51.packages.webui.backend.teamwork import (
    ConnectionManager,
    TeamworkState,
    canonical_frame_id,
    create_teamwork_router,
)


def test_canonical_frame_id_normalizes_numeric_frame():
    assert canonical_frame_id("L21_V001#12") == "L21_V001#000012"
    assert canonical_frame_id(" L21_V001#000012 ") == "L21_V001#000012"


def test_canonical_frame_id_rejects_malformed_values():
    for value in (None, "", "L21_V001", "L21 V001#1", "L21_V001#-1", "L21_V001#abc", "A#1#2"):
        assert canonical_frame_id(value) == ""


def test_state_add_is_newest_first_and_deduplicated():
    state = TeamworkState()
    assert state.add({"frame_id": "L21_V001#1", "sender": "a"}, added_at="t1") is True
    assert state.add({"frame_id": "L21_V001#2", "sender": "b"}, added_at="t2") is True
    assert state.add({"frame_id": "L21_V001#1", "sender": "other"}, added_at="t3") is False
    snapshot = state.snapshot()
    assert [item["frame_id"] for item in snapshot] == ["L21_V001#000002", "L21_V001#000001"]
    assert snapshot[1]["sender"] == "a"


def test_state_cap_keeps_newest_entries():
    state = TeamworkState(max_items=3)
    for frame in range(5):
        state.add({"frame_id": f"L21_V001#{frame}"}, added_at=str(frame))
    assert [item["frame"] for item in state.snapshot()] == [4, 3, 2]


def test_state_remove_and_clear():
    state = TeamworkState()
    state.add({"frame_id": "L21_V001#1"})
    state.add({"frame_id": "L21_V001#2"})
    assert state.remove("L21_V001#1") is True
    assert state.remove("L21_V001#1") is False
    assert [item["frame"] for item in state.snapshot()] == [2]
    assert state.clear() is True
    assert state.clear() is False
    assert state.snapshot() == []


def test_state_snapshot_is_not_mutable_alias():
    state = TeamworkState()
    state.add({"frame_id": "L21_V001#1", "note": "original"})
    snapshot = state.snapshot()
    snapshot[0]["note"] = "changed"
    assert state.snapshot()[0]["note"] == "original"


def _app_with_teamwork():
    app = FastAPI()
    state = TeamworkState()
    manager = ConnectionManager()
    app.include_router(create_teamwork_router(state, manager))
    return app, state, manager


def _recv(ws):
    return json.loads(ws.receive_text())


def test_two_websocket_clients_receive_authoritative_snapshots():
    app, state, manager = _app_with_teamwork()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/team") as first:
            assert _recv(first) == {"type": "team_sync", "data": []}
            with client.websocket_connect("/ws/team") as second:
                assert _recv(second) == {"type": "team_sync", "data": []}

                first.send_json({
                    "type": "add_frame",
                    "data": {"frame_id": "L21_V001#12", "sender": "alpha", "note": "candidate"},
                })
                first_sync = _recv(first)
                second_sync = _recv(second)
                assert first_sync["type"] == "team_sync"
                assert second_sync == first_sync
                assert first_sync["data"][0]["frame_id"] == "L21_V001#000012"
                assert first_sync["data"][0]["sender"] == "alpha"

                second.send_json({"type": "remove_frame", "data": {"frame_id": "L21_V001#12"}})
                assert _recv(first) == {"type": "team_sync", "data": []}
                assert _recv(second) == {"type": "team_sync", "data": []}

            # Disconnecting second must not break first.
            first.send_json({"type": "ping", "data": {"timestamp": "x"}})
            assert _recv(first) == {"type": "pong", "data": {"timestamp": "x"}}
            assert manager.connection_count == 1

    assert manager.connection_count == 0
    assert state.snapshot() == []


def test_websocket_rejects_invalid_identity_without_mutating_state():
    app, state, _ = _app_with_teamwork()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/team") as ws:
            assert _recv(ws) == {"type": "team_sync", "data": []}
            ws.send_json({"type": "add_frame", "data": {"frame_id": "bad"}})
            error = _recv(ws)
            assert error["type"] == "error"
            assert state.snapshot() == []
