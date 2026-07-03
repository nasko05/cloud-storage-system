"""Agent configuration, derived from the app settings.

Kept separate from ``app.config`` so the agent's knobs (and the API key) live in
one small object the routes and the loop pass around, and so tests can swap it
via a FastAPI dependency override without touching the global settings.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import DEFAULT_AGENT_MODEL, DEFAULT_OPENROUTER_BASE_URL, settings


@dataclass(frozen=True)
class AgentConfig:
    api_key: str
    model: str
    base_url: str
    max_steps: int

    @property
    def is_configured(self) -> bool:
        """Whether an OpenRouter key is present. Without it the chat endpoint is
        disabled and the UI hides the assistant."""
        return bool(self.api_key.strip())

    @classmethod
    def from_settings(cls) -> AgentConfig:
        return cls(
            api_key=settings.openrouter_api_key.strip(),
            model=(settings.agent_model or DEFAULT_AGENT_MODEL).strip(),
            base_url=(settings.openrouter_base_url or DEFAULT_OPENROUTER_BASE_URL).strip().rstrip("/"),
            # Clamp to a sane range so a typo can't run an unbounded tool loop.
            max_steps=max(1, min(24, settings.agent_max_steps)),
        )


def get_agent_config() -> AgentConfig:
    """FastAPI dependency. The single seam tests override to flip the agent
    on/off and to keep it from reading the import-time settings singleton."""
    return AgentConfig.from_settings()
