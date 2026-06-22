"""Uniform JSON error handling.

Handlers raise :class:`ApiError`; a single exception handler renders it as
``{"error": "..."}`` with the right status code, matching the contract the
React client already expects.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, message: str, **extra: object) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.extra = extra

    def to_response(self) -> JSONResponse:
        return JSONResponse(status_code=self.status_code, content={"error": self.message, **self.extra})


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return exc.to_response()


async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": "Internal server error"})
