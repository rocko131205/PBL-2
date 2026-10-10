"""FinVeritas API entry point.

Run locally:  uvicorn api.main:app --reload
In production the built React app (web/dist) is served from the same origin.
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from api.deps import client_ip  # noqa: E402
from api import jobs  # noqa: E402
from api.limits import BodyLimitMiddleware  # noqa: E402
from api.routers import analysis, auth, history, ingest, security  # noqa: E402
from finveritas.security import audit  # noqa: E402
from finveritas.security.config import validate_startup  # noqa: E402

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail closed: never serve with a missing or default signing secret.
    problems = validate_startup()
    if problems:
        raise RuntimeError("Server security configuration is incomplete:\n" + "\n".join(problems))
    try:
        jobs.recover_interrupted()
    except Exception as exc:  # the DB may be briefly unreachable at boot; requests will report it
        print(f"[startup] could not check for interrupted analyses: {type(exc).__name__}", file=sys.stderr)
    yield


app = FastAPI(title="FinVeritas API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(BodyLimitMiddleware)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    audit.set_client_ip(client_ip(request))
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(ingest.router)
app.include_router(analysis.router)
app.include_router(history.router)
app.include_router(security.router)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    detail = exc.detail
    body = detail if isinstance(detail, dict) else {"detail": detail}
    return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))


# ── Single-page app (only present after `npm run build`) ─────────────────────
if WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        candidate = (WEB_DIST / path).resolve()
        if path and candidate.is_file() and WEB_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
