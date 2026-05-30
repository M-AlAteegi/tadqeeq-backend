"""Optional bearer-token gate for /api/* endpoints.

If `settings.api_key` is empty (the dev default), this middleware is a
no-op — requests pass through unchanged. If a key is configured, every
/api/* request must carry `Authorization: Bearer <key>` or get a 401.

/health and /docs are always reachable so health checks + OpenAPI work
even on a locked-down deploy.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

_EXEMPT_PATHS = ("/health", "/docs", "/openapi.json", "/redoc")


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        configured = settings.api_key
        if not configured:
            return await call_next(request)
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in _EXEMPT_PATHS):
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or token != configured:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid bearer token."},
            )
        return await call_next(request)
