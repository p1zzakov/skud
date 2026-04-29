"""WebSocket менеджер — рассылка событий всем подключённым клиентам."""
import asyncio
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSManager:
    def __init__(self):
        self.connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.connections.append(ws)
        logger.info(f"WS connected. Total: {len(self.connections)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self.connections:
                self.connections.remove(ws)
        logger.info(f"WS disconnected. Total: {len(self.connections)}")

    async def broadcast(self, message: dict):
        if not self.connections:
            return
        data = json.dumps(message, ensure_ascii=False, default=str)
        dead = []
        async with self._lock:
            conns = list(self.connections)
        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


ws_manager = WSManager()
