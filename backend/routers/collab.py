"""Live collaboration: WebSocket channel, section locks and threaded section comments."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from auth import require_admin, require_user, user_from_token
from database import SessionLocal, get_db
from models import SectionComment, SectionLock, User
from realtime import hub
from schemas import CommentIn, CommentUpdate, LockIn

router = APIRouter(tags=["collaboration"])
LOCK_MINUTES = 15


# -------------------------------------------------------------------- locks ---
def lock_out(lk: SectionLock) -> dict:
    return {"term": lk.term, "section_id": lk.section_id, "user_id": lk.user_id, "user_name": lk.user_name,
            "acquired_at": lk.acquired_at, "expires_at": lk.expires_at}


def purge_expired(db: Session):
    expired = db.query(SectionLock).filter(SectionLock.expires_at < datetime.utcnow()).all()
    for lk in expired:
        db.delete(lk)
        hub.publish({"type": "lock", "term": lk.term, "section_id": lk.section_id, "lock": None})
    if expired:
        db.commit()


def active_lock(db: Session, term: str, section_id: str) -> Optional[SectionLock]:
    purge_expired(db)
    return db.query(SectionLock).filter_by(term=term, section_id=section_id).first()


def assert_editable(db: Session, term: str, section_id: str, user: User):
    """Raise 423 if another scheduler holds the lock; refresh our own lock."""
    lk = active_lock(db, term, section_id)
    if lk and lk.user_id != user.id:
        raise HTTPException(423, f"{section_id} is locked by {lk.user_name}")
    if lk:
        lk.expires_at = datetime.utcnow() + timedelta(minutes=LOCK_MINUTES)


@router.get("/api/locks")
def list_locks(term: str, db: Session = Depends(get_db)):
    purge_expired(db)
    return [lock_out(lk) for lk in db.query(SectionLock).filter(SectionLock.term == term).all()]


@router.post("/api/locks")
def acquire_lock(body: LockIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    lk = active_lock(db, body.term, body.section_id)
    if lk and lk.user_id != user.id:
        raise HTTPException(409, f"Already locked by {lk.user_name}")
    if not lk:
        lk = SectionLock(term=body.term, section_id=body.section_id, user_id=user.id, user_name=user.name)
        db.add(lk)
    lk.acquired_at = lk.acquired_at or datetime.utcnow()
    lk.expires_at = datetime.utcnow() + timedelta(minutes=LOCK_MINUTES)
    db.commit()
    out = lock_out(lk)
    hub.publish({"type": "lock", "term": body.term, "section_id": body.section_id, "lock": out})
    return out


@router.delete("/api/locks", status_code=204)
def release_lock(term: str, section_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    lk = active_lock(db, term, section_id)
    if not lk:
        return
    # Owners release normally; another admin may break a stale lock deliberately.
    db.delete(lk)
    db.commit()
    hub.publish({"type": "lock", "term": term, "section_id": section_id, "lock": None,
                 "broken_by": user.name if lk.user_id != user.id else None})


# ----------------------------------------------------------------- comments ---
def comment_out(c: SectionComment) -> dict:
    return {"id": c.id, "term": c.term, "section_id": c.section_id, "parent_id": c.parent_id,
            "user_id": c.user_id, "author_name": c.author_name, "body": c.body, "resolved": c.resolved,
            "created_at": c.created_at}


@router.get("/api/comments")
def list_comments(term: str, section_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(SectionComment).filter(SectionComment.term == term)
    if section_id:
        q = q.filter(SectionComment.section_id == section_id)
    return [comment_out(c) for c in q.order_by(SectionComment.created_at).all()]


@router.post("/api/comments", status_code=201)
def add_comment(body: CommentIn, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if body.parent_id:
        parent = db.get(SectionComment, body.parent_id)
        if not parent or parent.section_id != body.section_id or parent.term != body.term:
            raise HTTPException(404, "Parent comment not found on this section")
    c = SectionComment(term=body.term, section_id=body.section_id, parent_id=body.parent_id, user_id=user.id,
                       author_name=user.name, body=body.body.strip())
    db.add(c)
    db.commit()
    out = comment_out(c)
    hub.publish({"type": "comment", "action": "created", "term": c.term, "section_id": c.section_id, "comment": out})
    return out


@router.patch("/api/comments/{cid}")
def update_comment(cid: int, body: CommentUpdate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = db.get(SectionComment, cid)
    if not c:
        raise HTTPException(404, "Comment not found")
    if body.body is not None:
        if c.user_id != user.id:
            raise HTTPException(403, "Only the author can edit a comment")
        c.body = body.body.strip()
    if body.resolved is not None:
        if c.user_id != user.id and user.role != "admin":
            raise HTTPException(403, "Only the author or a scheduler can resolve a thread")
        c.resolved = body.resolved
    db.commit()
    out = comment_out(c)
    hub.publish({"type": "comment", "action": "updated", "term": c.term, "section_id": c.section_id, "comment": out})
    return out


@router.delete("/api/comments/{cid}", status_code=204)
def delete_comment(cid: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = db.get(SectionComment, cid)
    if not c:
        raise HTTPException(404, "Comment not found")
    if c.user_id != user.id and user.role != "admin":
        raise HTTPException(403, "Only the author or a scheduler can delete a comment")
    term, section_id = c.term, c.section_id
    db.delete(c)
    db.commit()
    hub.publish({"type": "comment", "action": "deleted", "term": term, "section_id": section_id, "comment": {"id": cid}})


# ---------------------------------------------------------------- websocket ---
def _ws_user(token: Optional[str]) -> Optional[dict]:
    with SessionLocal() as db:
        u = user_from_token(db, token)
        return {"id": u.id, "name": u.name, "role": u.role} if u else None


def _release_user_locks(user_id: int) -> list[tuple[str, str]]:
    with SessionLocal() as db:
        locks = db.query(SectionLock).filter(SectionLock.user_id == user_id).all()
        released = [(lk.term, lk.section_id) for lk in locks]
        for lk in locks:
            db.delete(lk)
        db.commit()
        return released


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: Optional[str] = None):
    """
    Live channel. Anonymous clients receive updates; signed-in clients also appear
    in presence. Clients may send {"type":"presence","page","term","section_id"}
    and {"type":"ping"}.
    """
    user = await run_in_threadpool(_ws_user, token)
    await hub.connect(ws, user)
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "ping":
                await ws.send_json({"type": "pong"})
            elif kind == "presence":
                hub.update(ws, page=msg.get("page"), term=msg.get("term"), section_id=msg.get("section_id"))
                await hub.broadcast_presence()
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        await hub.disconnect(ws)
        # A scheduler who closes their last tab releases their locks
        if user and not hub.user_connected(user["id"]):
            for term, section_id in await run_in_threadpool(_release_user_locks, user["id"]):
                await hub.broadcast({"type": "lock", "term": term, "section_id": section_id, "lock": None})
