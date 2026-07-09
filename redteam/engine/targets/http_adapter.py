"""
Generic HTTP chat-API adapter.

Works against any deployed advice API that accepts a JSON POST and returns
either a plain JSON text field or an Asaas-style SSE stream of
`{"event": "content", "delta": ...}` frames terminated by `{"event": "done"}`.
This is what makes the engine usable against a second/third team's advice API
for a real cross-market red-team run, not just Asaas.

Requires `httpx` (not a hard dependency of the rest of the engine).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class HTTPTargetConfig:
    base_url: str
    chat_path: str = "/chat"
    auth_header: str | None = None  # e.g. "Bearer <token>"
    message_field: str = "message"
    session_field: str = "conversation_id"
    # "sse" (Asaas-style content-delta stream) or "json" (single JSON response)
    response_mode: str = "sse"
    json_text_path: tuple[str, ...] = ("response",)  # dotted path if response_mode="json"
    timeout_s: float = 30.0
    extra_headers: dict[str, str] = field(default_factory=dict)


class HTTPChatAdapter:
    """Deployment-agnostic adapter — implements engine.targets.base.TargetAdapter."""

    def __init__(self, config: HTTPTargetConfig):
        self.config = config

    async def new_session(self, persona_name: str, setup: dict) -> str:
        # Generic HTTP targets have no fixture-provisioning hook — the caller
        # is responsible for pointing the engine at an account already in the
        # state a scenario needs (documented per-scenario in `setup`).
        return str(uuid.uuid4())

    async def send(self, session_id: str, message: str) -> str:
        cfg = self.config
        headers = dict(cfg.extra_headers)
        if cfg.auth_header:
            headers["Authorization"] = cfg.auth_header

        payload = {cfg.message_field: message, cfg.session_field: session_id}

        async with httpx.AsyncClient(timeout=cfg.timeout_s) as client:
            if cfg.response_mode == "sse":
                return await self._send_sse(client, headers, payload)
            return await self._send_json(client, headers, payload)

    async def get_state(self, session_id: str) -> dict:
        return {}

    # -- internal ----------------------------------------------------------

    async def _send_sse(
        self, client: httpx.AsyncClient, headers: dict, payload: dict
    ) -> str:
        url = self.config.base_url.rstrip("/") + self.config.chat_path
        chunks: list[str] = []
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    frame = json.loads(line[len("data: "):])
                except json.JSONDecodeError:
                    continue
                if frame.get("event") == "content":
                    chunks.append(frame.get("delta", ""))
                elif frame.get("event") == "done":
                    break
        return "".join(chunks)

    async def _send_json(
        self, client: httpx.AsyncClient, headers: dict, payload: dict
    ) -> str:
        url = self.config.base_url.rstrip("/") + self.config.chat_path
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data: Any = resp.json()
        for key in self.config.json_text_path:
            data = data[key]
        return str(data)
