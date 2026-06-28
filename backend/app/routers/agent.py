"""AI reorganization assistant: status, chat (propose), and apply (approve)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..agent.apply import apply_plan
from ..agent.client import OpenRouterClient, get_chat_client
from ..agent.config import AgentConfig, get_agent_config
from ..agent.loop import run_turn
from ..deps import CurrentUser, get_current_user, get_db
from ..errors import ApiError
from ..schemas import AgentApplyRequest, AgentChatRequest

router = APIRouter(prefix="/v2/agent", tags=["agent"])

# Bounds on the conversation a single request may carry. The server is stateless
# between turns, so the whole history rides along each time; clamp it to bound
# request size and token spend.
MAX_MESSAGES = 200
MAX_TOTAL_CHARS = 600_000


@router.get("/status")
def status(
    user: CurrentUser = Depends(get_current_user),
    cfg: AgentConfig = Depends(get_agent_config),
) -> dict:
    """Whether the assistant is usable, and which model. Session-gated so the
    server config isn't exposed to anonymous probes."""
    return {"configured": cfg.is_configured, "model": cfg.model}


@router.post("/chat")
def chat(
    payload: AgentChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    cfg: AgentConfig = Depends(get_agent_config),
    client: OpenRouterClient = Depends(get_chat_client),
) -> dict:
    """Run one agent turn. The request shape is validated before the
    configured-key check so a malformed call is rejected identically whether or
    not a provider key is set."""
    messages = payload.messages
    if not messages:
        raise ApiError(400, "messages must not be empty")
    if len(messages) > MAX_MESSAGES:
        raise ApiError(400, "conversation is too long; start a new chat")
    total = sum(len(content) for m in messages if isinstance(content := m.get("content"), str))
    if total > MAX_TOTAL_CHARS:
        raise ApiError(400, "conversation is too large; start a new chat")
    if messages[-1].get("role") not in ("user", "tool"):
        raise ApiError(400, "the last message must be from the user or a tool result")

    if not cfg.is_configured:
        raise ApiError(400, "the AI assistant is not configured on this server")

    return run_turn(client, db, user.id, messages, max_steps=cfg.max_steps)


@router.post("/apply")
def apply(
    payload: AgentApplyRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Apply an approved plan transactionally. Works without an API key — only
    the chat (proposal) step needs the model."""
    applied = apply_plan(db, user.id, payload.operations)
    return {"applied": applied}
