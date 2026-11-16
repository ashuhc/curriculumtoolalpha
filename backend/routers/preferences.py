"""Faculty teaching-preference submissions."""
from __future__ import annotations

from datetime import datetime
from typing import List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

import services as svc
from auth import require_admin, require_user
from database import get_db
from models import Course, Faculty, PreferenceSubmission, User
from schemas import PreferenceIn, PreferenceOut

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


def _out(s: PreferenceSubmission) -> PreferenceOut:
    return PreferenceOut(id=s.id, faculty_id=s.faculty_id, faculty_name=s.faculty.name,
                         submitted_at=s.submitted_at, email=s.email, principles=s.principles or [],
                         ranks=s.ranks or [], fall_target=s.fall_target, spring_target=s.spring_target,
                         overload=s.overload, overload_semester=s.overload_semester,
                         unique_circumstances=s.unique_circumstances or "", submitted_by=s.submitted_by)


@router.post("", response_model=PreferenceOut, status_code=201)
def submit(body: PreferenceIn, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Any signed-in user may submit for a roster instructor (themselves by default, or on
    someone's behalf); the submitter is recorded on every submission for auditing."""
    f = db.get(Faculty, body.faculty_id)
    if not f or not f.active:
        raise HTTPException(404, "Faculty member not found")
    known = {c.code for c in db.query(Course).filter(Course.active.is_(True)).all()}
    unknown = [c for c in body.ranks if c not in known]
    if unknown:
        raise HTTPException(422, "Unknown course(s): " + ", ".join(f"ECON {c}" for c in unknown))
    data = body.model_dump()
    if not data["overload"]:
        data["overload_semester"] = "None"
    elif data["overload_semester"] == "None":
        raise HTTPException(422, "Choose which semester you are overloading")
    s = PreferenceSubmission(**data, submitted_at=datetime.utcnow(), submitted_by=f"{user.name} <{user.email}>"[:200])
    db.add(s)
    if not f.email:
        f.email = body.email
    db.commit()
    svc.bump_version("preferences")
    return _out(s)


@router.get("/mine", response_model=List[PreferenceOut])
def mine(db: Session = Depends(get_db), user: User = Depends(require_user)):
    if user.faculty_id is None:
        return []
    return [_out(s) for s in db.query(PreferenceSubmission).filter(PreferenceSubmission.faculty_id == user.faculty_id)
            .order_by(PreferenceSubmission.submitted_at.desc()).all()]


@router.get("", response_model=List[PreferenceOut])
def list_all(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [_out(s) for s in db.query(PreferenceSubmission).order_by(PreferenceSubmission.submitted_at.desc()).all()]


@router.delete("/{pid}", status_code=204)
def delete_one(pid: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = db.get(PreferenceSubmission, pid)
    if not s:
        raise HTTPException(404, "Submission not found")
    db.delete(s)
    db.commit()
    svc.bump_version("preferences")


@router.delete("", status_code=204)
def clear_all(confirm: bool = Query(False), db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not confirm:
        raise HTTPException(400, "Pass ?confirm=true to delete every submission")
    db.query(PreferenceSubmission).delete()
    db.commit()
    svc.bump_version("preferences")


@router.get("/export")
def export(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """CSV in the same column layout TEACHER_PREFERENCES.py wrote."""
    titles = svc.catalog(db, include_inactive=True)
    label = lambda c: f"ECON {c} - {titles.get(c, '')}"  # noqa: E731
    rows = []
    for s in db.query(PreferenceSubmission).order_by(PreferenceSubmission.submitted_at).all():
        ranks = list(s.ranks or []) + [None] * 6
        rows.append({
            "Timestamp": s.submitted_at.strftime("%Y-%m-%d %H:%M:%S"), "Full Name": s.faculty.name,
            "Email": s.email, "Principles Preferences": "; ".join(label(c) for c in s.principles) or "None",
            **{f"Rank {i + 1} Course": label(ranks[i]) if ranks[i] else "None" for i in range(6)},
            "Fall Desired Courses": s.fall_target, "Spring Desired Courses": s.spring_target,
            "Course Overload": "Yes" if s.overload else "No", "Overload Semester": s.overload_semester,
            "Unique Circumstances": s.unique_circumstances or "None",
            "Submitted By": s.submitted_by or "",
        })
    return Response(pd.DataFrame(rows).to_csv(index=False), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="teacher_preferences_export.csv"'})
