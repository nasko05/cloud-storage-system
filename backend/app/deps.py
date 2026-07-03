"""Reusable FastAPI dependencies: DB session and authenticated principal."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header

from .database import get_db
from .errors import ApiError
from .security import decode_access_token

__all__ = ["get_db", "CurrentUser", "get_current_user", "IdempotencyKey"]

# Shared parameter default for the Idempotency-Key header, so every mutating
# route declares it identically: `idempotency_key: str | None = IdempotencyKey`.
IdempotencyKey = Header(default=None, alias="Idempotency-Key")


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "Unauthorized")
    token = authorization.split(" ", 1)[1].strip()
    claims = decode_access_token(token)
    if not claims or not claims.get("sub"):
        raise ApiError(401, "Unauthorized")
    return CurrentUser(id=claims["sub"], email=claims.get("email", claims["sub"]))


CurrentUserDep = Depends(get_current_user)
