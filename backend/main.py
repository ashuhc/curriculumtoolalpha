"""
main.py — FastAPI application for the NU Economics Automated Course Scheduler.

    uvicorn main:app --reload          (from /backend, after `python seed_db.py`)

REST docs: http://localhost:8000/docs   ·   live channel: ws://localhost:8000/ws?token=…

Access model
    anonymous  read-only dashboards (demand, schedule, conflicts, catalog), exports
    faculty    + submit own teaching preferences, comment on sections
    admin      + overrides, section locks, publishing, catalog/faculty/user management
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from realtime import hub
from routers import auth_routes, catalog, collab, data, planning, preferences

CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://localhost:8080")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()                                   # create any missing tables (seed_db.py populates them)
    hub.bind_loop(asyncio.get_running_loop())   # lets sync endpoints broadcast WebSocket events
    yield


app = FastAPI(title="NU Economics Course Scheduler API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in CORS_ORIGINS.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])

for r in (auth_routes, catalog, preferences, planning, collab, data):
    app.include_router(r.router)
