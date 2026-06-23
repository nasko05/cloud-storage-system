"""In-memory login rate limiting with temporary lockout.

Suitable for a single-instance, low-traffic deployment. Failed login attempts
are tracked per ``email + client IP``; after too many failures within the window
the key is locked out for a cooldown period. Thresholds are read from settings at
call time so tests can tune them.
"""

from __future__ import annotations

import threading
import time

from .config import settings


class LoginRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (failure_timestamps, locked_until)
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    @staticmethod
    def _key(email: str, client_ip: str | None) -> str:
        return f"{(email or '').strip().lower()}|{client_ip or '-'}"

    def check_locked(self, email: str, client_ip: str | None) -> int:
        """Return remaining lockout seconds (0 if not locked)."""
        key = self._key(email, client_ip)
        now = time.time()
        with self._lock:
            until = self._locked_until.get(key, 0)
            if until > now:
                return int(until - now)
            if until:
                # Lockout expired; clear it.
                self._locked_until.pop(key, None)
                self._failures.pop(key, None)
            return 0

    def register_failure(self, email: str, client_ip: str | None) -> None:
        key = self._key(email, client_ip)
        now = time.time()
        window = settings.login_window_seconds
        with self._lock:
            attempts = [t for t in self._failures.get(key, []) if now - t < window]
            attempts.append(now)
            self._failures[key] = attempts
            if len(attempts) >= settings.login_max_attempts:
                self._locked_until[key] = now + settings.login_lockout_seconds

    def register_success(self, email: str, client_ip: str | None) -> None:
        key = self._key(email, client_ip)
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()


login_rate_limiter = LoginRateLimiter()
