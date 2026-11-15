"""
WebSocket hub for live collaboration.

Every connected browser receives JSON events:
    {"type": "presence",  "users": [...]}                    who is online and where
    {"type": "schedule",  "term", "section_id", "by"}        an override changed
    {"type": "lock",      "term", "section_id", "lock"|null} a section was (un)locked
    {"type": "comment",   "term", "section_id", "comment"}   a comment was added/updated/deleted
    {"type": "data",      "scope"}                           catalog/faculty/preferences/enrollment changed
    {"type": "published", "term", "publication"}             a schedule was published

Sync (threadpool) endpoints call `hub.publish(...)`, which hands the broadcast to
the event loop thread-safely. The hub is in-process: run a single API process,
or swap this for Redis pub/sub when scaling horizontally.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import WebSocket


class Hub:
    def __init__(self):
        self.connections: dict[WebSocket, dict] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    async def connect(self, ws: WebSocket, user: Optional[dict]):
        await ws.accept()
        self.connections[ws] = {"user": user, "page": None, "term": None, "section_id": None}
        await self.broadcast_presence()

    async def disconnect(self, ws: WebSocket) -> Optional[dict]:
        info = self.connections.pop(ws, None)
        await self.broadcast_presence()
        return info

    def user_connected(self, user_id: int) -> bool:
        return any((c["user"] or {}).get("id") == user_id for c in self.connections.values())

    def update(self, ws: WebSocket, **fields):
        if ws in self.connections:
            self.connections[ws].update({k: v for k, v in fields.items() if k in ("page", "term", "section_id")})

    def presence(self) -> list[dict]:
        seen: dict[int, dict] = {}
        guests = 0
        for c in self.connections.values():
            u = c["user"]
            if not u:
                guests += 1
                continue
            seen[u["id"]] = {**u, "page": c["page"], "term": c["term"], "section_id": c["section_id"]}
        return list(seen.values()) + ([{"id": 0, "name": f"{guests} guest(s)", "role": "guest"}] if guests else [])

    async def broadcast(self, message: dict):
        data = json.dumps(message, default=str)
        dead = []
        for ws in list(self.connections):
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001 — client vanished mid-send
                dead.append(ws)
        for ws in dead:
            self.connections.pop(ws, None)

    async def broadcast_presence(self):
        await self.broadcast({"type": "presence", "users": self.presence()})

    def publish(self, message: dict):
        """Thread-safe fire-and-forget broadcast (callable from sync endpoints)."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)


hub = Hub()
