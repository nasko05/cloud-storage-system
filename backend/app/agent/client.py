"""Minimal client for an OpenRouter-style (OpenAI-compatible) chat-completions
API. We model only the slice the agent loop needs: messages, tool/function
calls, and tool definitions.

The constructor accepts an optional ``httpx.Client`` so tests inject an
``httpx.MockTransport`` and never touch the network.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Depends

from ..errors import ApiError
from .config import AgentConfig, get_agent_config

Message = dict[str, Any]
ToolDef = dict[str, Any]

_REQUEST_TIMEOUT_SECONDS = 120.0


class OpenRouterClient:
    def __init__(self, cfg: AgentConfig, *, http: httpx.Client | None = None) -> None:
        self._endpoint = f"{cfg.base_url}/chat/completions"
        self._model = cfg.model
        self._api_key = cfg.api_key
        self._http = http or httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS)

    def chat(self, messages: list[Message], tools: list[ToolDef]) -> Message:
        """Send the conversation + tool catalogue and return the assistant's next
        message (which may itself carry tool calls)."""
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.3,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            resp = self._http.post(self._endpoint, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ApiError(502, "AI provider request failed") from exc

        if resp.status_code >= 400:
            raise _map_provider_error(resp.status_code)

        try:
            data = resp.json()
        except ValueError as exc:
            raise ApiError(502, "AI provider returned an unreadable response") from exc

        choices = data.get("choices") or []
        if not choices:
            raise ApiError(502, "AI provider returned no choices")

        message = choices[0].get("message") or {}
        _fill_missing_tool_call_ids(message)
        return message


def _map_provider_error(status_code: int) -> ApiError:
    """Map a non-2xx from the provider onto something the operator can act on.
    4xx (other than rate limiting) usually means a bad key or model id."""
    if status_code == 429:
        return ApiError(429, "The AI provider is rate limiting requests; try again shortly")
    if status_code < 500:
        return ApiError(
            400,
            "The AI provider rejected the request. Check DRIVE_OPENROUTER_API_KEY and DRIVE_AGENT_MODEL.",
        )
    return ApiError(502, "The AI provider is currently unavailable")


def _fill_missing_tool_call_ids(message: Message) -> None:
    """Give every tool call a non-empty id (some open-weight models omit it),
    synthesising one from its position so the matching tool result can be
    threaded back. Provider-supplied ids are left untouched."""
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        return
    for index, call in enumerate(calls):
        if isinstance(call, dict) and not str(call.get("id") or "").strip():
            call["id"] = f"call_{index}"


def get_chat_client(cfg: AgentConfig = Depends(get_agent_config)) -> OpenRouterClient:
    """FastAPI dependency. Tests override this to return a client backed by an
    ``httpx.MockTransport``."""
    return OpenRouterClient(cfg)
