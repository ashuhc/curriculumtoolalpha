"""
Service layer: turns database rows into engine inputs, runs the planning
pipeline with an in-process cache, and serialises results for the API.

The cache key is (settings, data_version). Every mutating endpoint calls
bump_version(), so planners always see live data; manual schedule overrides
are layered on afterwards and never invalidate the (expensive) base plan.
"""
from __future__ import annotations

import json
import re
import threading
from collections import OrderedDict

import pandas as pd
from sqlalchemy.orm import Session

import engine as eng
from realtime import hub
from models import Course, EnrollmentRecord, Faculty, PreferenceSubmission, ScheduleOverride

_lock = threading.Lock()
_version = 0
_plan_cache: "OrderedDict[tuple, dict]" = OrderedDict()
_enr_cache: dict = {}
CACHE_SIZE = 24


def bump_version(scope: str = "data"):
    """Invalidate caches after any data change and tell connected clients to refresh."""
    global _version
    with _lock:
        _version += 1
        _plan_cache.clear()
        _enr_cache.clear()
    hub.publish({"type": "data", "scope": scope})


# ------------------------------------------------------------------ inputs ---
def raw_enrollment(db: Session) -> pd.DataFrame:
    """Enrollment rows as a DataFrame with the original spreadsheet column names."""
    key = ("raw", _version)
    if key not in _enr_cache:
        rows = db.query(EnrollmentRecord).all()
        _enr_cache[key] = pd.DataFrame([{
            "ACADEMIC_PERIOD_DESC": r.academic_period, "CAMPUS": r.campus, "Course #": r.course_number,
            "Course Title": r.course_title, "CRN": r.crn, "Instructional Method": r.instructional_method,
            "Instructor": r.instructor, "Schedule": r.schedule,
            "MAXIMUM_ENROLLMENT": r.maximum_enrollment, "UG_ENROLLMENT": r.ug_enrollment,
        } for r in rows], columns=eng.REQUIRED_ENROLLMENT_COLUMNS + ["CRN"])
    return _enr_cache[key]


def clean_enrollment(db: Session) -> pd.DataFrame:
    key = ("clean", _version)
    if key not in _enr_cache:
        raw = raw_enrollment(db)
        _enr_cache[key] = eng.load_enrollment(raw) if not raw.empty else pd.DataFrame()
    return _enr_cache[key]


def catalog(db: Session, include_inactive=False) -> dict[int, str]:
    q = db.query(Course)
    if not include_inactive:
        q = q.filter(Course.active.is_(True))
    return {c.code: c.title for c in q.all() if c.code < 5000}


def preferences(db: Session) -> dict[str, dict]:
    """Latest submission per active faculty member, in engine format."""
    latest: dict[int, PreferenceSubmission] = {}
    for s in db.query(PreferenceSubmission).order_by(PreferenceSubmission.submitted_at).all():
        latest[s.faculty_id] = s
    out = {}
    for s in latest.values():
        if not s.faculty.active:
            continue
        sem = s.overload_semester if s.overload else "None"
        if s.overload and sem == "None":
            sem = "Both"
        out[s.faculty.name] = {
            "ranks": [int(c) for c in s.ranks or []], "principles": [int(c) for c in s.principles or []],
            "Fall": s.fall_target, "Spring": s.spring_target, "overload": s.overload,
            "overload_semester": sem, "circumstances": s.unique_circumstances or "",
        }
    return out


def active_faculty(db: Session) -> list[Faculty]:
    return db.query(Faculty).filter(Faculty.active.is_(True)).order_by(Faculty.name).all()


def overloads(faculty: list[Faculty]) -> dict:
    return {f.name: {"overloading": f.overload.overloading, "semester": f.overload.semester}
            for f in faculty if f.overload}


def inferred_roster(db: Session, faculty: list[Faculty]) -> pd.DataFrame:
    enr = clean_enrollment(db)
    if enr.empty:
        return pd.DataFrame(columns=["Faculty", "Type", "Annual Reduction", "UG Lectures / Yr (hist.)",
                                     "Grad Sections / Yr (hist.)", "Source"])
    key = ("roster", _version)
    if key not in _enr_cache:
        roster = eng.infer_roster(enr, [f.name for f in faculty], saved={})
        # Admin-confirmed groups win; a confirmed group without an explicit
        # reduction keeps the history-inferred reduction (grad teaching).
        for f in faculty:
            if f.faculty_type:
                mask = roster["Faculty"] == f.name
                roster.loc[mask, "Type"] = f.faculty_type
                roster.loc[mask, "Source"] = "Confirmed"
                if f.annual_reduction is not None:
                    roster.loc[mask, "Annual Reduction"] = f.annual_reduction
        _enr_cache[key] = roster
    return _enr_cache[key]


# ---------------------------------------------------------------- planning ---
def to_settings(ps) -> eng.Settings:
    return eng.Settings(**ps.model_dump())


def run_plan(db: Session, ps) -> dict:
    key = (json.dumps(ps.model_dump(), sort_keys=True), _version)
    with _lock:
        if key in _plan_cache:
            _plan_cache.move_to_end(key)
            return _plan_cache[key]
    raw = raw_enrollment(db)
    if raw.empty:
        raise ValueError("No enrollment data in the database. Run `python seed_db.py` first.")
    faculty = active_faculty(db)
    result = eng.run_pipeline(
        raw, to_settings(ps), prefs=preferences(db), faculty=[f.name for f in faculty],
        overloads=overloads(faculty), catalog=catalog(db), roster_override=inferred_roster(db, faculty),
    )
    with _lock:
        _plan_cache[key] = result
        while len(_plan_cache) > CACHE_SIZE:
            _plan_cache.popitem(last=False)
    return result


def overrides_for(db: Session, term: str) -> dict[str, dict]:
    return {o.section_id: {"instructor": o.instructor, "sequence": o.sequence}
            for o in db.query(ScheduleOverride).filter(ScheduleOverride.term == term).all()}


def schedule(db: Session, ps) -> dict:
    """Base plan + manual overrides, with conflicts & workload recomputed on the edited table."""
    res = run_plan(db, ps)
    settings = to_settings(ps)
    ovr = overrides_for(db, settings.target_term)
    master, applied = eng.apply_overrides(res["master"], ovr, res["profiles"])
    conflicts = eng.detect_conflicts(master, res["profiles"], settings, res["prereq"], res["dropped"],
                                     res["pref_warnings"])
    workload = eng.workload_summary(master, res["profiles"], settings)
    return {**res, "master": master, "conflicts": conflicts, "workload": workload,
            "overrides_applied": applied, "overrides_stale": sorted(set(ovr) - set(applied))}


# ----------------------------------------------------------- serialisation ---
def snake(name: str) -> str:
    s = re.sub(r"\(if known\)", "", str(name))
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_").lower()
    return s


def records(df: pd.DataFrame, rename: dict | None = None, drop_private=True) -> list[dict]:
    """DataFrame -> JSON-safe list of dicts with snake_case keys (NaN -> null)."""
    if df is None or df.empty:
        return []
    d = df.rename(columns=rename or {})
    if drop_private:
        d = d[[c for c in d.columns if not str(c).startswith("_")]]
    d = d.rename(columns=snake)
    return json.loads(d.to_json(orient="records", date_format="iso"))


def workload_frame(wl: pd.DataFrame, sem: str) -> pd.DataFrame:
    if wl.empty:
        return wl
    return wl.rename(columns={f"{sem} Target": "Term Target", f"Assigned ({sem})": "Assigned This Term"})


def demand_frame(demand: pd.DataFrame) -> pd.DataFrame:
    d = demand.copy()
    d["Code"] = d["_code"]
    d["Virtual"] = d["_virtual"]
    d["Core"] = d["_core"]
    return d


def term_options(db: Session) -> dict:
    enr = clean_enrollment(db)
    known = sorted({(s, y) for s, y in zip(enr["sem"], enr["year"])}, key=lambda p: eng.term_ordinal(*p)) \
        if not enr.empty else []
    latest = eng.term_ordinal(*known[-1]) if known else eng.term_ordinal("Fall", 2026)
    upcoming = [f"{'Fall' if (latest + k) % 2 else 'Spring'} {(latest + k) // 2}" for k in range(1, 5)]
    return {"upcoming": upcoming, "historical": [f"{s} {y}" for s, y in reversed(known)],
            "default": upcoming[0]}


def sequence_meta() -> dict:
    def pack(seqs: dict, kind: str):
        out = {}
        for code, blocks in seqs.items():
            days, time = eng.describe_slot(code)
            out[code] = {"code": code, "kind": kind, "days": days, "label": time,
                         "blocks": [{"day": d, "start": s, "end": e} for d, s, e in blocks]}
        return out

    return {
        "class": pack(eng.CLASS_SEQUENCES, "class"),
        "lab": pack(eng.LAB_SEQUENCES, "lab"),
        "recitation": pack(eng.RECITATION_SLOTS, "recitation"),
        "special": [eng.ASYNC_SLOT, eng.UNSCHEDULED],
    }


def to_csv(df: pd.DataFrame) -> str:
    return df.to_csv(index=False)


def catalog_export(rows: list[dict], term: str) -> pd.DataFrame:
    """
    Registrar-style export: one row per meeting pattern (sequence H meets at two
    different times, so it produces two rows). Times are 24h HH:MM.
    """
    out = []
    for r in rows:
        code = r["course"].split()[-1]
        base = {
            "Term": term, "Subject": "ECON", "Course Number": code, "Section": r["section"],
            "Title": r["title"], "Component": "REC" if r["component"] == "Recitation" else "LEC",
            "Instructional Method": "Online" if str(r["modality"]).startswith("Online") else "In Person",
            "Capacity": r["section_cap"], "Instructor": r["instructor"], "Sequence": r["sequence"],
            "Linked Lecture": r.get("linked_lecture") or "",
        }
        blocks = eng.ALL_SLOTS.get(r["sequence"])
        if not blocks:
            out.append({**base, "Days": "", "Start Time": "", "End Time": ""})
            continue
        patterns: dict[tuple, str] = {}
        for d, s, e in blocks:
            patterns[(s, e)] = patterns.get((s, e), "") + d
        for (s, e), days in sorted(patterns.items()):
            out.append({**base, "Days": days, "Start Time": f"{s // 60:02d}:{s % 60:02d}",
                        "End Time": f"{e // 60:02d}:{e % 60:02d}"})
    cols = ["Term", "Subject", "Course Number", "Section", "Title", "Component", "Instructional Method",
            "Capacity", "Days", "Start Time", "End Time", "Sequence", "Instructor", "Linked Lecture"]
    return pd.DataFrame(out, columns=cols)
