"""In-memory WebSocket connection registry, scoped per "channel" (a queue
entry id, sim room id, or tournament id string), with an associated user_id
per connection so targeted (not just broadcast) sends are possible - used for
the automaton_flagged message, which must reach only that automaton's owner.

In-memory, single-process - matches this project's current scale. Horizontally
scaling the web tier later would need a shared pub/sub layer here too; same
documented-upgrade-path shape as the nsjail->gVisor and no-Redis-yet notes
elsewhere in this project.
"""

from __future__ import annotations

import contextlib
import uuid
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[tuple[WebSocket, uuid.UUID]]] = defaultdict(list)

    async def connect(self, channel: str, websocket: WebSocket, user_id: uuid.UUID) -> None:
        await websocket.accept()
        self._connections[channel].append((websocket, user_id))

    def disconnect(self, channel: str, websocket: WebSocket) -> None:
        conns = self._connections.get(channel)
        if not conns:
            return
        remaining = [(ws, uid) for ws, uid in conns if ws is not websocket]
        if remaining:
            self._connections[channel] = remaining
        else:
            del self._connections[channel]

    def member_count(self, channel: str) -> int:
        return len(self._connections.get(channel, []))

    async def broadcast(
        self, channel: str, message: dict, *, target_user_id: uuid.UUID | None = None
    ) -> None:
        for ws, uid in list(self._connections.get(channel, [])):
            if target_user_id is not None and uid != target_user_id:
                continue
            with contextlib.suppress(Exception):
                # A dead connection here is handled by its own receive loop's
                # disconnect - a broadcast failure is not this call's problem.
                await ws.send_json(message)


matchmaking_manager = ConnectionManager()
sim_room_manager = ConnectionManager()
tournament_manager = ConnectionManager()
