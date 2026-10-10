"""Request-size limits, enforced before any body is parsed.

Starlette reads and spools a whole multipart body before an endpoint (or its auth dependency) runs,
so the per-file checks inside the endpoints can't protect memory or disk on their own. This ASGI
middleware caps the total body per route, both by the declared Content-Length and by counting bytes as
they arrive (which also covers chunked uploads that declare no length).
"""
from __future__ import annotations

import json

from finveritas.security.uploads import MAX_PDF_BYTES, MAX_PDF_FILES, MAX_SHEET_BYTES

_OVERHEAD = 1 * 1024 * 1024        # multipart boundaries, form fields
DEFAULT_LIMIT = 1 * 1024 * 1024    # every JSON endpoint
LIMITS = {
    "/api/ingest/pdf": MAX_PDF_FILES * MAX_PDF_BYTES + _OVERHEAD,
    "/api/ingest/csv": MAX_SHEET_BYTES + _OVERHEAD,
}
SESSION_COOKIE = b"fv_session="


class BodyTooLarge(Exception):
    pass


def limit_for(path: str) -> int:
    return LIMITS.get(path, DEFAULT_LIMIT)


async def _reply(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)

        path = scope["path"]
        headers = dict(scope["headers"])
        # Upload endpoints parse large multipart bodies before authentication runs, so turn away
        # requests that carry no session at all without reading a byte. (Full validation still
        # happens in the endpoint's dependency.)
        if path in LIMITS and SESSION_COOKIE not in headers.get(b"cookie", b""):
            return await _reply(send, 401, "Not authenticated.")

        limit = limit_for(path)
        declared = headers.get(b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            return await _reply(send, 413, "That request is too large.")

        received = 0
        started = False

        async def counting_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except BodyTooLarge:
            if not started:
                await _reply(send, 413, "That request is too large.")
