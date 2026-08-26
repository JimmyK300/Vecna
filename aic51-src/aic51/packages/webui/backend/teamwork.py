"""Bounded realtime shared shortlist adapted from OpenCubee for Vecna Issue #71.

The primitive is intentionally independent of retrieval, Milvus, submissions, and
benchmark semantics. State is process-local and resets when the backend restarts.
"""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

MAX_MESSAGE_BYTES = 64 * 1024
MAX_TEAMWORK_FRAMES = 200
MAX_SENDER_CHARS = 80
MAX_NOTE_CHARS = 500

DONOR_REPOSITORY = "k19tvan/Opencubee2"
DONOR_COMMIT = "0412b55a0f9a3c9642805a669efd871fddf3e970"
DONOR_SOURCE = "backend/api/realtime.py + backend/core/runtime.py::ConnectionManager"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_frame_id(value: Any) -> str:
    """Return canonical `video_id#frame_id` or an empty string if invalid."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if value.count("#") != 1:
        return ""
    video_id, frame_text = value.split("#", 1)
    video_id = video_id.strip()
    frame_text = frame_text.strip()
    if not video_id or any(ch.isspace() for ch in video_id):
        return ""
    try:
        frame = int(frame_text)
    except ValueError:
        return ""
    if frame < 0:
        return ""
    return f"{video_id}#{frame:06d}"


def _bounded_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


class TeamworkState:
    """Deterministic newest-first process-local shortlist state."""

    def __init__(self, max_items: int = MAX_TEAMWORK_FRAMES):
        self.max_items = max(1, int(max_items))
        self._items: list[dict[str, Any]] = []

    def snapshot(self) -> list[dict[str, Any]]:
        return deepcopy(self._items)

    def add(self, data: dict[str, Any], *, added_at: str | None = None) -> bool:
        frame_id = canonical_frame_id(data.get("frame_id"))
        if not frame_id:
            raise ValueError("add_frame requires canonical frame_id `video_id#frame_id`")
        if any(item["frame_id"] == frame_id for item in self._items):
            return False
        video_id, frame_text = frame_id.split("#", 1)
        item = {
            "frame_id": frame_id,
            "video_id": video_id,
            "frame": int(frame_text),
            "sender": _bounded_text(data.get("sender"), MAX_SENDER_CHARS),
            "note": _bounded_text(data.get("note"), MAX_NOTE_CHARS),
            "added_at": added_at or utc_now(),
        }
        self._items.insert(0, item)
        del self._items[self.max_items :]
        return True

    def remove(self, frame_id: Any) -> bool:
        frame_id = canonical_frame_id(frame_id)
        if not frame_id:
            raise ValueError("remove_frame requires canonical frame_id `video_id#frame_id`")
        before = len(self._items)
        self._items = [item for item in self._items if item["frame_id"] != frame_id]
        return len(self._items) != before

    def clear(self) -> bool:
        changed = bool(self._items)
        self._items = []
        return changed


class ConnectionManager:
    """Small WebSocket connection set with per-socket send serialization."""

    def __init__(self):
        self._connections: dict[WebSocket, asyncio.Lock] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[websocket] = asyncio.Lock()

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    async def send_text(self, websocket: WebSocket, message: str) -> bool:
        lock = self._connections.get(websocket)
        if lock is None:
            return False
        try:
            async with lock:
                await asyncio.wait_for(websocket.send_text(message), timeout=5.0)
            return True
        except Exception:
            self.disconnect(websocket)
            return False

    async def broadcast(self, message: str) -> None:
        connections = list(self._connections)
        if connections:
            await asyncio.gather(
                *(self.send_text(connection, message) for connection in connections),
                return_exceptions=True,
            )

    @property
    def connection_count(self) -> int:
        return len(self._connections)


def encode_event(message_type: str, data: Any) -> str:
    return json.dumps({"type": message_type, "data": data}, ensure_ascii=False, separators=(",", ":"))


def create_teamwork_router(
    state: TeamworkState | None = None,
    manager: ConnectionManager | None = None,
) -> APIRouter:
    state = state or TeamworkState()
    manager = manager or ConnectionManager()
    state_lock = asyncio.Lock()
    router = APIRouter()

    async def send_event(websocket: WebSocket, message_type: str, data: Any) -> bool:
        return await manager.send_text(websocket, encode_event(message_type, data))

    async def broadcast_snapshot() -> None:
        await manager.broadcast(encode_event("team_sync", state.snapshot()))

    @router.get("/api/team_shortlist")
    async def team_shortlist_snapshot():
        async with state_lock:
            return {
                "status": "success",
                "items": state.snapshot(),
                "connection_count": manager.connection_count,
                "persistence": "process_local_memory",
            }

    @router.websocket("/ws/team")
    async def teamwork_socket(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            async with state_lock:
                synced = await send_event(websocket, "team_sync", state.snapshot())
            if not synced:
                return

            while True:
                raw = await websocket.receive_text()
                if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                    await websocket.close(code=1009, reason="WebSocket message is too large")
                    return
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await send_event(websocket, "error", {"detail": "Message must be valid JSON."})
                    continue
                if not isinstance(message, dict):
                    await send_event(websocket, "error", {"detail": "Message must be a JSON object."})
                    continue
                message_type = message.get("type")
                data = message.get("data") or {}
                if not isinstance(data, dict):
                    await send_event(websocket, "error", {"detail": "Message data must be a JSON object."})
                    continue

                if message_type == "ping":
                    await send_event(websocket, "pong", {"timestamp": data.get("timestamp")})
                    continue

                try:
                    async with state_lock:
                        if message_type == "add_frame":
                            state.add(data)
                        elif message_type == "remove_frame":
                            state.remove(data.get("frame_id"))
                        elif message_type == "clear_panel":
                            state.clear()
                        else:
                            await send_event(
                                websocket,
                                "error",
                                {"detail": f"Unsupported message type: {message_type!r}."},
                            )
                            continue
                        await broadcast_snapshot()
                except ValueError as exc:
                    await send_event(websocket, "error", {"detail": str(exc)})

        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect(websocket)

    # Test/review hooks are explicit attributes, not public HTTP behavior.
    router.teamwork_state = state  # type: ignore[attr-defined]
    router.teamwork_manager = manager  # type: ignore[attr-defined]
    return router
