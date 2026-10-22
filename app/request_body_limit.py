"""Streaming ASGI request-size guard for API write endpoints.

This middleware buffers at most the configured limit before dispatch so multipart parsers
cannot consume an unbounded chunked request when Content-Length is absent. Keep a gateway
body limit in public deployments as an additional control.
"""
from __future__ import annotations

import re
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class RequestBodyLimitMiddleware:
    """Reject oversized API write bodies, including chunked bodies without a length header."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") not in {"POST", "PUT", "PATCH"}
            or not str(scope.get("path", "")).startswith("/v1/")
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        declared_length = headers.get(b"content-length")
        if declared_length is not None:
            try:
                if int(declared_length) > self.max_bytes:
                    await self._reject(scope, send)
                    return
            except ValueError:
                # The application guard returns a 400 for malformed Content-Length.
                await self.app(scope, receive, send)
                return

        chunks = bytearray()
        while True:
            message = await receive()
            message_type = message.get("type")
            if message_type == "http.disconnect":
                return
            if message_type != "http.request":
                continue
            body = message.get("body", b"")
            if not isinstance(body, bytes):
                await self._reject(scope, send)
                return
            if len(chunks) + len(body) > self.max_bytes:
                await self._reject(scope, send)
                return
            chunks.extend(body)
            if not message.get("more_body", False):
                break

        body_bytes = bytes(chunks)
        delivered = False

        async def replay_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        raw_headers = dict(scope.get("headers", []))
        supplied_id = raw_headers.get(b"x-correlation-id", b"").decode("latin-1")
        correlation_id = supplied_id if _CORRELATION_ID.fullmatch(supplied_id) else str(uuid4())
        body = b'{"detail":"Request body exceeds the configured limit."}'
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"x-correlation-id", correlation_id.encode("ascii")),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (b"cache-control", b"no-store"),
        ]
        await send({"type": "http.response.start", "status": 413, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})
