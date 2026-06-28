"""The agent HTTP endpoints: status, chat validation, auth gating."""

import httpx
import pytest
from conftest import auth_header, register_and_login

from app.agent.client import OpenRouterClient, get_chat_client
from app.agent.config import AgentConfig, get_agent_config
from app.main import app


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _set_config(api_key="sk-test"):
    cfg = AgentConfig(api_key=api_key, model="test-model", base_url="https://x/api/v1", max_steps=8)
    app.dependency_overrides[get_agent_config] = lambda: cfg


def _set_chat(response):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response)

    cfg = AgentConfig(api_key="sk-test", model="test-model", base_url="https://x/api/v1", max_steps=8)
    chat = OpenRouterClient(cfg, http=httpx.Client(transport=httpx.MockTransport(handler)))
    app.dependency_overrides[get_chat_client] = lambda: chat


def _assistant(content=None, tool_calls=None):
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def test_status_unconfigured(client):
    token, _, _ = register_and_login(client)
    _set_config(api_key="")
    resp = client.get("/v2/agent/status", headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json() == {"configured": False, "model": "test-model"}


def test_status_configured(client):
    token, _, _ = register_and_login(client)
    _set_config(api_key="sk-test")
    body = client.get("/v2/agent/status", headers=auth_header(token)).json()
    assert body["configured"] is True
    assert body["model"] == "test-model"


def test_chat_happy_path(client):
    token, _, _ = register_and_login(client)
    _set_config()
    _set_chat(_assistant(content="Hi! How can I help tidy your drive?"))
    resp = client.post(
        "/v2/agent/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
        headers=auth_header(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["done"] is True
    assert body["assistant_text"].startswith("Hi!")
    assert body["pending_actions"] == []


def test_chat_returns_proposal(client):
    token, _, _ = register_and_login(client)
    _set_config()
    _set_chat(
        _assistant(
            content="Proposing.",
            tool_calls=[
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "create_folder", "arguments": '{"parentPath":"/","name":"Photos"}'},
                }
            ],
        )
    )
    resp = client.post(
        "/v2/agent/chat",
        json={"messages": [{"role": "user", "content": "make a Photos folder"}]},
        headers=auth_header(token),
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["done"] is False
    assert body["pending_actions"][0]["tool"] == "create_folder"
    assert "Photos" in body["pending_actions"][0]["summary"]


def test_chat_empty_messages_rejected(client):
    token, _, _ = register_and_login(client)
    _set_config()
    assert client.post("/v2/agent/chat", json={"messages": []}, headers=auth_header(token)).status_code == 400


def test_chat_oversized_rejected(client):
    token, _, _ = register_and_login(client)
    _set_config()
    huge = {"messages": [{"role": "user", "content": "x" * 600_001}]}
    assert client.post("/v2/agent/chat", json=huge, headers=auth_header(token)).status_code == 400


def test_chat_last_message_role_validated(client):
    token, _, _ = register_and_login(client)
    _set_config()
    body = {"messages": [{"role": "assistant", "content": "hi"}]}
    assert client.post("/v2/agent/chat", json=body, headers=auth_header(token)).status_code == 400


def test_chat_unconfigured_rejected(client):
    token, _, _ = register_and_login(client)
    _set_config(api_key="")
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/v2/agent/chat", json=body, headers=auth_header(token)).status_code == 400


def test_agent_endpoints_require_auth(client):
    assert client.get("/v2/agent/status").status_code == 401
    assert client.post("/v2/agent/chat", json={"messages": []}).status_code == 401
    assert client.post("/v2/agent/apply", json={"operations": []}).status_code == 401
