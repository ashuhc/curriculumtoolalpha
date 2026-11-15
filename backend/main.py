"""
main.py — FastAPI application for the NU Economics Automated Course Scheduler.

    uvicorn main:app --reload          (from /backend, after `python seed_db.py`)

REST docs: http://localhost:8000/docs   ·   live channel: ws://localhost:8000/ws?token=…

Access model
    anonymous  read-only dashboards, exports      (blocked entirely when REQUIRE_LOGIN=true)
    faculty    + submit own teaching preferences, comment on sections
    admin      + overrides, section locks, publishing, catalog/faculty/user management

Single-container hosting: set STATIC_DIR to the built frontend (frontend/dist) and
this app also serves the website from the same origin (used by the root Dockerfile / Render).
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from auth import decode_token, login_required
from database import init_db
from realtime import hub
from routers import auth_routes, catalog, collab, data, planning, preferences

CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://localhost:8080")
STATIC_DIR = os.environ.get("STATIC_DIR", "")
# Reachable without signing in even when REQUIRE_LOGIN=true
PUBLIC_API = {"/api/health", "/api/auth/login", "/api/meta"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()                                   # create any missing tables (seed_db.py populates them)
    hub.bind_loop(asyncio.get_running_loop())   # lets sync endpoints broadcast WebSocket events
    yield


app = FastAPI(title="NU Economics Course Scheduler API", version="2.1.0", lifespan=lifespan)


@app.middleware("http")
async def sign_in_gate(request: Request, call_next):
    """With REQUIRE_LOGIN=true, every /api call except PUBLIC_API needs a valid bearer token."""
    path = request.url.path
    if (login_required() and path.startswith("/api/") and path not in PUBLIC_API
            and request.method != "OPTIONS"):
        auth = request.headers.get("authorization", "")
        if not (auth.lower().startswith("bearer ") and decode_token(auth[7:].strip())):
            return JSONResponse({"detail": "Sign in required"}, status_code=401)
    return await call_next(request)


# Added last so it wraps everything (401s from the gate still carry CORS headers)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in CORS_ORIGINS.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])

for r in (auth_routes, catalog, preferences, planning, collab, data):
    app.include_router(r.router)


# ------------------------------------------------------------------ website ---
if STATIC_DIR and os.path.isfile(os.path.join(STATIC_DIR, "index.html")):
    _root = os.path.realpath(STATIC_DIR)
    app.mount("/assets", StaticFiles(directory=os.path.join(_root, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """Serve built files; any other path falls back to index.html (client-side routing)."""
        if full_path.startswith(("api/", "ws")):
            raise HTTPException(404)
        candidate = os.path.realpath(os.path.join(_root, full_path))
        if full_path and candidate.startswith(_root + os.sep) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_root, "index.html"), headers={"Cache-Control": "no-cache"})
