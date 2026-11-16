"""Demand forecasting, master schedule, manual overrides, publishing and exports."""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

import engine as eng
import services as svc
from auth import login_required, require_admin
from database import get_db
from models import Publication, ScheduleOverride, SectionComment, SectionLock, User
from realtime import hub
from routers.collab import active_lock, assert_editable, lock_out, purge_expired
from schemas import OverrideIn, OverrideOut, PlanRequest, PublishIn

router = APIRouter(prefix="/api", tags=["planning"])


def _plan_or_400(fn, db, ps):
    try:
        return fn(db, ps)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _csv(df: pd.DataFrame, filename: str) -> Response:
    return Response(df.to_csv(index=False), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    return {
        "terms": svc.term_options(db),
        "sequences": svc.sequence_meta(),
        "faculty_types": dict(eng.FACULTY_TYPES),
        "core": {"econ_at_nu": eng.ECON_AT_NU, "principles": eng.PRINCIPLES, "follow_ups": eng.FOLLOW_UPS,
                 "capstones": eng.CAPSTONES, "recitations": eng.RECITATION_FOR},
        "limits": {"virtual_cap": eng.VIRTUAL_CAP_LIMIT},
        "special_instructors": [eng.UNSTAFFED, eng.RECITATION_TBA],
        "require_login": login_required(),
    }


@router.post("/plan/demand")
def plan_demand(body: PlanRequest, db: Session = Depends(get_db)):
    res = _plan_or_400(svc.run_plan, db, body.settings)
    d = res["demand"]
    planned = d[d["Planned Sections"] > 0]
    lec = planned[planned["Category"] != "Recitation"]
    rec = planned[planned["Category"] == "Recitation"]
    return {
        "term": body.settings.target_term,
        "summary": {
            "courses": int(lec["_code"].nunique()), "lecture_sections": int(lec["Planned Sections"].sum()),
            "recitation_sections": int(rec["Planned Sections"].sum()),
            "projected_students": int(lec["Projected Enrollment"].sum()),
            "remote_sections": int(lec.loc[lec["_virtual"], "Planned Sections"].sum()),
            "seats_offered": int(lec["Seats Offered"].sum()),
        },
        "demand": svc.records(svc.demand_frame(d)),
        "prerequisites": svc.records(res["prereq"].rename(columns={"_ok": "ok"}), drop_private=False)
        if not res["prereq"].empty else [],
    }


def _schedule_payload(db: Session, body: PlanRequest) -> dict:
    res = _plan_or_400(svc.schedule, db, body.settings)
    m, c = res["master"], res["conflicts"]
    term = body.settings.target_term
    sem, _ = eng.parse_term_label(term)
    staffed = ~m["Instructor"].isin([eng.UNSTAFFED, eng.RECITATION_TBA]) if not m.empty else pd.Series(dtype=bool)
    core = m["Category"].str.startswith("Core") if not m.empty else pd.Series(dtype=bool)
    counts = c["Severity"].value_counts() if not c.empty else {}
    purge_expired(db)
    comment_counts: dict[str, int] = {}
    for sid, resolved in db.query(SectionComment.section_id, SectionComment.resolved).filter(
            SectionComment.term == term).all():
        if not resolved:
            comment_counts[sid] = comment_counts.get(sid, 0) + 1
    latest = db.query(Publication).filter(Publication.term == term).order_by(Publication.version.desc()).first()
    return {
        "term": term,
        "summary": {
            "sections": len(m), "core_sections": int(core.sum()), "core_staffed": int((staffed & core).sum()),
            "electives_offered": int(m.loc[m["Category"] == "Elective", "Course"].nunique()) if not m.empty else 0,
            "preference_matches": int(m["Match Basis"].str.contains("Rank [1-3]|Principles", regex=True).sum())
            if not m.empty else 0,
            "critical": int(counts.get("Critical", 0)), "warning": int(counts.get("Warning", 0)),
            "info": int(counts.get("Info", 0)), "submissions": len(res["prefs"]),
            "overrides_applied": len(res["overrides_applied"]), "overrides_stale": res["overrides_stale"],
        },
        "master": svc.records(m),
        "conflicts": svc.records(c),
        "workload": svc.records(svc.workload_frame(res["workload"], sem)),
        "instructors": sorted(res["profiles"]),
        "overridden": res["overrides_applied"],
        "locks": [lock_out(lk) for lk in db.query(SectionLock).filter(SectionLock.term == term).all()],
        "comment_counts": comment_counts,
        "publication": _pub_meta(latest) if latest else None,
        "_master_df": m, "_conflicts_df": c, "_workload_df": res["workload"],
    }


@router.post("/plan/schedule")
def plan_schedule(body: PlanRequest, db: Session = Depends(get_db)):
    p = _schedule_payload(db, body)
    return {k: v for k, v in p.items() if not k.startswith("_")}


# ---------------------------------------------------------------- overrides ---
@router.get("/plan/overrides", response_model=List[OverrideOut])
def list_overrides(term: str, db: Session = Depends(get_db)):
    return db.query(ScheduleOverride).filter(ScheduleOverride.term == term).all()


@router.put("/plan/overrides")
def upsert_override(body: OverrideIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    valid_seq = set(eng.ALL_SLOTS) | {eng.ASYNC_SLOT, eng.UNSCHEDULED}
    if body.sequence and body.sequence not in valid_seq:
        raise HTTPException(422, f"Unknown sequence '{body.sequence}'")
    if body.instructor:
        names = {f.name for f in svc.active_faculty(db)} | {eng.UNSTAFFED, eng.RECITATION_TBA}
        if body.instructor not in names:
            raise HTTPException(422, f"'{body.instructor}' is not an active faculty member")
    assert_editable(db, body.term, body.section_id, user)
    o = db.query(ScheduleOverride).filter_by(term=body.term, section_id=body.section_id).first()
    if not body.instructor and not body.sequence:
        if o:
            db.delete(o)
        db.commit()
        hub.publish({"type": "schedule", "term": body.term, "section_id": body.section_id, "by": user.name})
        return {"deleted": True}
    if not o:
        o = ScheduleOverride(term=body.term, section_id=body.section_id)
        db.add(o)
    o.instructor, o.sequence = body.instructor or None, body.sequence or None
    db.commit()
    hub.publish({"type": "schedule", "term": body.term, "section_id": body.section_id, "by": user.name})
    return {"id": o.id, "term": o.term, "section_id": o.section_id, "instructor": o.instructor, "sequence": o.sequence}


@router.delete("/plan/overrides")
def reset_overrides(term: str, section_id: Optional[str] = None, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    """Revert manual edits to the generated assignment: one section, or every section in the term.
    A bulk revert skips sections another scheduler currently has locked for editing."""
    q = db.query(ScheduleOverride).filter(ScheduleOverride.term == term)
    if section_id:
        assert_editable(db, term, section_id, user)
        q = q.filter(ScheduleOverride.section_id == section_id)
    reverted, skipped = [], []
    for o in q.all():
        lk = active_lock(db, term, o.section_id)
        if not section_id and lk and lk.user_id != user.id:
            skipped.append({"section_id": o.section_id, "locked_by": lk.user_name})
            continue
        reverted.append(o.section_id)
        db.delete(o)
    db.commit()
    if reverted:
        hub.publish({"type": "schedule", "term": term, "section_id": section_id, "by": user.name})
    return {"reverted": reverted, "skipped": skipped}


# --------------------------------------------------------------- publishing ---
def _pub_meta(p: Publication) -> dict:
    return {"id": p.id, "term": p.term, "version": p.version, "published_at": p.published_at,
            "published_by": p.published_by, "note": p.note, "sections": len(p.sections),
            "critical": p.critical, "warning": p.warning}


@router.get("/publications")
def list_publications(term: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Publication)
    if term:
        q = q.filter(Publication.term == term)
    return [_pub_meta(p) for p in q.order_by(Publication.published_at.desc()).all()]


@router.post("/publications", status_code=201)
def publish(body: PublishIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Freeze the current master schedule (incl. manual edits) as the official version for a term."""
    p = _schedule_payload(db, PlanRequest(settings=body.settings))
    critical = p["summary"]["critical"]
    if critical and not body.allow_critical:
        raise HTTPException(409, f"{critical} critical conflict(s) remain. Resolve them or publish anyway.")
    term = body.settings.target_term
    prev = db.query(Publication).filter(Publication.term == term).order_by(Publication.version.desc()).first()
    pub = Publication(term=term, version=(prev.version + 1) if prev else 1, published_by=user.name,
                      note=body.note.strip(), settings=body.settings.model_dump(), sections=p["master"],
                      critical=critical, warning=p["summary"]["warning"])
    db.add(pub)
    db.commit()
    meta_out = _pub_meta(pub)
    hub.publish({"type": "published", "term": term, "publication": meta_out})
    return meta_out


@router.get("/publications/{pid}/export")
def export_publication(pid: int, db: Session = Depends(get_db)):
    """Finalized master schedule in registrar/catalog-import layout."""
    p = db.get(Publication, pid)
    if not p:
        raise HTTPException(404, "Publication not found")
    slug = p.term.replace(" ", "_").lower()
    return _csv(svc.catalog_export(p.sections, p.term), f"econ_catalog_{slug}_v{p.version}.csv")


# ------------------------------------------------------------------ exports ---
@router.post("/export/{kind}")
def export(kind: str, body: PlanRequest, db: Session = Depends(get_db)):
    term = body.settings.target_term
    slug = term.replace(" ", "_").lower()
    if kind == "demand":
        res = _plan_or_400(svc.run_plan, db, body.settings)
        return _csv(res["demand"][[c for c in res["demand"].columns if not c.startswith("_")]],
                    f"demand_estimate_{slug}.csv")
    p = _schedule_payload(db, body)
    if kind == "catalog":
        return _csv(svc.catalog_export(p["master"], term), f"econ_catalog_{slug}_draft.csv")
    frames = {"master": (p["_master_df"], "master_schedule"), "conflicts": (p["_conflicts_df"], "unresolved_conflicts"),
              "workload": (p["_workload_df"], "faculty_workload")}
    if kind not in frames:
        raise HTTPException(404, "Export kind must be one of: demand, master, catalog, conflicts, workload")
    df, name = frames[kind]
    return _csv(df, f"{name}_{slug}.csv")
