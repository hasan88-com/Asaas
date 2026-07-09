"""
Verifies HTTPChatAdapter against a mocked transport — no real network/server
needed, but exercises the actual SSE-framing and JSON-path parsing code paths
end to end (not just unit-level string checks).
"""

from __future__ import annotations

import httpx
import pytest

from redteam.engine.targets.http_adapter import HTTPChatAdapter, HTTPTargetConfig


def _sse_body(deltas: list[str]) -> bytes:
    lines = [f'data: {{"event": "content", "delta": "{d}"}}\n\n' for d in deltas]
    lines.append('data: {"event": "done", "agentRole": "chat"}\n\n')
    return "".join(lines).encode()


@pytest.mark.asyncio
async def test_http_adapter_parses_asaas_style_sse_stream(monkeypatch):
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_body(["Here's ", "a ", "suggestion, not financial advice."]),
        )

    transport = httpx.MockTransport(handler)

    # Patch httpx.AsyncClient construction inside the adapter to use our transport.
    original_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory)

    adapter = HTTPChatAdapter(HTTPTargetConfig(base_url="http://fake-target", response_mode="sse"))
    session_id = await adapter.new_session("persona", {})
    response = await adapter.send(session_id, "hello")

    assert response == "Here's a suggestion, not financial advice."
    assert len(captured_requests) == 1
    assert captured_requests[0].url.path == "/chat"


@pytest.mark.asyncio
async def test_http_adapter_parses_json_response(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "plain json reply"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory)

    adapter = HTTPChatAdapter(
        HTTPTargetConfig(base_url="http://fake-target", response_mode="json", json_text_path=("response",))
    )
    session_id = await adapter.new_session("persona", {})
    response = await adapter.send(session_id, "hello")

    assert response == "plain json reply"


@pytest.mark.asyncio
async def test_http_adapter_sends_auth_header(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=_sse_body(["hi"]))

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory)

    adapter = HTTPChatAdapter(
        HTTPTargetConfig(base_url="http://fake-target", auth_header="Bearer test-token")
    )
    session_id = await adapter.new_session("persona", {})
    await adapter.send(session_id, "hello")

    assert captured["auth"] == "Bearer test-token"
