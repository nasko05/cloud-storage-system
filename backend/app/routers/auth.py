"""Built-in email/password auth (replacement for Amazon Cognito)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import get_db
from ..errors import ApiError
from ..models import User
from ..ratelimit import login_rate_limiter
from ..schemas import ConfirmRequest, LoginRequest, RegisterRequest
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/v2/auth", tags=["auth"])


def _find_user(db: Session, email: str) -> User | None:
    stmt = select(User).where(func.lower(User.email) == email.strip().lower())
    return db.execute(stmt).scalars().first()


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    if _find_user(db, email) is not None:
        raise ApiError(409, "An account with that email already exists")

    requires_confirmation = settings.require_email_confirmation
    code = f"{secrets.randbelow(1_000_000):06d}" if requires_confirmation else None
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        is_confirmed=not requires_confirmation,
        confirmation_code=code,
    )
    db.add(user)
    db.flush()

    if requires_confirmation:
        # Self-hosted deployments have no mailer; surface the code in the logs.
        print(f"[auth] confirmation code for {email}: {code}")

    return {
        "userId": user.id,
        "email": user.email,
        "confirmationRequired": requires_confirmation,
    }


@router.post("/confirm")
def confirm(payload: ConfirmRequest, db: Session = Depends(get_db)) -> dict:
    user = _find_user(db, payload.email)
    if user is None:
        raise ApiError(404, "Account not found")
    if not user.is_confirmed:
        if settings.require_email_confirmation and user.confirmation_code != payload.code.strip():
            raise ApiError(400, "Invalid confirmation code")
        user.is_confirmed = True
        user.confirmation_code = None
        db.flush()
    return {"confirmed": True}


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    client_ip = request.client.host if request.client else None
    locked_for = login_rate_limiter.check_locked(payload.email, client_ip)
    if locked_for:
        raise ApiError(429, f"Too many attempts. Try again in {locked_for} seconds.")

    user = _find_user(db, payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        login_rate_limiter.register_failure(payload.email, client_ip)
        raise ApiError(401, "Incorrect email or password")
    if not user.is_confirmed:
        raise ApiError(403, "Account is not confirmed yet")

    login_rate_limiter.register_success(payload.email, client_ip)
    return {
        "token": create_access_token(user.id, user.email),
        "userId": user.id,
        "email": user.email,
    }
