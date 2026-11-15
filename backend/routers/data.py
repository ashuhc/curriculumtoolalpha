"""Health check and historical enrollment data."""
from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

import engine as eng
import services as svc
from auth import require_admin
from database import get_db
from models import Course, EnrollmentRecord, Faculty, PreferenceSubmission, User

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": db.bind.dialect.name,
            "enrollment_records": db.query(EnrollmentRecord).count(), "courses": db.query(Course).count(),
            "faculty": db.query(Faculty).count(), "submissions": db.query(PreferenceSubmission).count()}


@router.get("/enrollment/terms")
def enrollment_terms(db: Session = Depends(get_db)):
    enr = svc.clean_enrollment(db)
    if enr.empty:
        return []
    ug = enr[~enr["is_grad"]]
    g = ug.groupby(["ordinal", "term"]).agg(sections=("course", "size"), students=("ug_enr", "sum")).reset_index()
    return [{"term": r.term, "sections": int(r.sections), "students": int(r.students)}
            for r in g.sort_values("ordinal", ascending=False).itertuples()]


@router.post("/enrollment/upload")
async def upload_enrollment(file: UploadFile = File(...), db: Session = Depends(get_db),
                            _: User = Depends(require_admin)):
    from seed_db import records_from_frame

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content)) if (file.filename or "").lower().endswith(".csv") \
            else pd.read_excel(io.BytesIO(content))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not read file: {e}")
    missing = eng.validate_enrollment_columns(df)
    if missing:
        raise HTTPException(422, "Missing columns: " + ", ".join(missing))
    rows = records_from_frame(df)
    db.add_all(EnrollmentRecord(**r) for r in rows)
    db.commit()
    svc.bump_version("enrollment")
    return {"added": len(rows)}
