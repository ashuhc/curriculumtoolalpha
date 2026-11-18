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
from models import Course, EnrollmentRecord, Faculty, ManualSection, Overload, PreferenceSubmission, ScheduleOverride

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


def baseline_overloads() -> dict:
    """Default overload approvals: the seeded faculty_overloads.json (missing file = none)."""
    if "baseline_overloads" not in _enr_cache:
        _enr_cache["baseline_overloads"] = eng.load_overloads()
    return _enr_cache["baseline_overloads"]


def baseline_overload_for(name: str) -> tuple[bool, str]:
    b = baseline_overloads().get(name) or {}
    on = bool(b.get("overloading"))
    sem = str(b.get("semester", "None")).title() if on else "None"
    return on, ("Both" if on and sem == "None" else sem)


def customized_fields(f: Faculty) -> list[str]:
    """Which roster settings differ from the inferred / seeded baseline."""
    out = []
    if f.faculty_type:
        out.append("Faculty Group")
    if f.fall_courseload is not None:
        out.append("Fall Courseload")
    if f.spring_courseload is not None:
        out.append("Spring Courseload")
    on = bool(f.overload and f.overload.overloading)
    cur = (on, f.overload.semester if on else "None")
    if cur != baseline_overload_for(f.name):
        out.append("Approved Overload")
    return out


def reset_faculty_to_default(f: Faculty) -> bool:
    """Restore inferred group, automatic courseloads and the seeded overload. Returns True if anything changed."""
    changed = bool(customized_fields(f)) or f.annual_reduction is not None
    f.faculty_type = f.annual_reduction = f.fall_courseload = f.spring_courseload = None
    on, sem = baseline_overload_for(f.name)
    if on:
        if not f.overload:
            f.overload = Overload(overloading=True, semester=sem)
        f.overload.overloading, f.overload.semester = True, sem
    elif f.overload:
        f.overload.overloading, f.overload.semester = False, "None"
    return changed


def active_faculty(db: Session) -> list[Faculty]:
    return db.query(Faculty).filter(Faculty.active.is_(True)).order_by(Faculty.name).all()


def overloads(faculty: list[Faculty]) -> dict:
    return {f.name: {"overloading": f.overload.overloading, "semester": f.overload.semester}
            for f in faculty if f.overload}


def inferred_roster(db: Session, faculty: list[Faculty]) -> pd.DataFrame:
    enr = clean_enrollment(db)
    if enr.empty:
        return pd.DataFrame(columns=["Faculty", "Type", "Annual Reduction", "UG Lectures / Yr (hist.)",
                                     "Grad Sections / Yr (hist.)", "Source", "Fall Courseload", "Spring Courseload"])
    key = ("roster", _version)
    if key not in _enr_cache:
        roster = eng.infer_roster(enr, [f.name for f in faculty], saved={})
        # Admin-confirmed groups win. Scheduler-set semester courseloads (Administration →
        # Faculty & Overloads) override form/history term targets; blank = not set.
        roster["Fall Courseload"] = None
        roster["Spring Courseload"] = None
        roster = roster.astype({"Fall Courseload": object, "Spring Courseload": object})
        for f in faculty:
            mask = roster["Faculty"] == f.name
            if f.faculty_type:
                roster.loc[mask, "Type"] = eng.normalize_faculty_type(f.faculty_type)
                roster.loc[mask, "Source"] = "Confirmed"
            roster.loc[mask, "Fall Courseload"] = f.fall_courseload
            roster.loc[mask, "Spring Courseload"] = f.spring_courseload
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
    return {o.section_id: {"instructor": o.instructor, "sequence": o.sequence, "cap": o.cap, "removed": bool(o.removed)}
            for o in db.query(ScheduleOverride).filter(ScheduleOverride.term == term).all()}


# ------------------------------------------------- undo / redo section state ---
def section_state(db: Session, term: str, section_id: str) -> dict:
    """Snapshot of a section's scheduler edits: its override row and/or hand-added section row."""
    o = db.query(ScheduleOverride).filter_by(term=term, section_id=section_id).first()
    ms = db.query(ManualSection).filter_by(term=term, section_id=section_id).first()
    return {
        "section_id": section_id,
        "override": {"instructor": o.instructor, "sequence": o.sequence, "cap": o.cap, "removed": bool(o.removed)} if o else None,
        "manual": {"code": ms.code, "section": ms.section, "title": ms.title, "instructor": ms.instructor,
                   "virtual": bool(ms.virtual), "sequence": ms.sequence, "cap": ms.cap,
                   "created_by": ms.created_by or ""} if ms else None,
    }


def _state_key(state: dict) -> tuple:
    """Comparable form of a snapshot (who created a manual section doesn't matter)."""
    o, m = state.get("override"), state.get("manual")
    ok = None if not o else (o.get("instructor") or None, o.get("sequence") or None, o.get("cap"), bool(o.get("removed")))
    mk = None if not m else (int(m["code"]), str(m["section"]), m.get("title") or "", m.get("instructor") or None,
                             bool(m.get("virtual")), m.get("sequence") or None, int(m["cap"]))
    if ok == (None, None, None, False):
        ok = None
    return ok, mk


def same_state(a: dict, b: dict) -> bool:
    return _state_key(a) == _state_key(b)


def write_section_state(db: Session, term: str, state: dict) -> None:
    """Make the section's edit rows match `state` exactly (caller commits)."""
    sid = state["section_id"]
    o = db.query(ScheduleOverride).filter_by(term=term, section_id=sid).first()
    ms = db.query(ManualSection).filter_by(term=term, section_id=sid).first()
    want_o, want_m = state.get("override"), state.get("manual")
    if want_o and _state_key({"override": want_o})[0] is None:
        want_o = None
    if want_o is None:
        if o:
            db.delete(o)
    else:
        if not o:
            o = ScheduleOverride(term=term, section_id=sid)
            db.add(o)
        o.instructor, o.sequence = want_o.get("instructor") or None, want_o.get("sequence") or None
        o.cap, o.removed = want_o.get("cap"), bool(want_o.get("removed"))
    if want_m is None:
        if ms:
            db.delete(ms)
    else:
        if not ms:
            ms = ManualSection(term=term, section_id=sid)
            db.add(ms)
        for k in ("code", "section", "title", "instructor", "virtual", "sequence", "cap"):
            setattr(ms, k, want_m.get(k))
        ms.created_by = want_m.get("created_by") or ms.created_by or ""


def manual_sections_for(db: Session, term: str) -> list[ManualSection]:
    return db.query(ManualSection).filter(ManualSection.term == term).order_by(ManualSection.section_id).all()


def manual_out(ms: ManualSection) -> dict:
    return {"id": ms.id, "term": ms.term, "section_id": ms.section_id, "code": ms.code, "section_no": int(ms.section),
            "title": ms.title, "instructor": ms.instructor, "modality": "Remote" if ms.virtual else "In-Person",
            "sequence": ms.sequence, "cap": ms.cap, "created_by": ms.created_by or ""}


def _manual_projection(res: dict, code: int, virtual: bool) -> int:
    """Students a hand-added section can expect: the unoffered elective's demand, else the unseated overflow."""
    for sec in res.get("dropped", []):
        if sec["code"] == code and bool(sec["virtual"]) == virtual:
            return int(sec["projected"])
    for u in res.get("unseated", []):
        if u["code"] == code and u["virtual"] == virtual:
            return int(u["unseated"])
    return 0


def schedule(db: Session, ps) -> dict:
    """Base plan + hand-added sections + manual overrides, with conflicts & workload recomputed."""
    res = run_plan(db, ps)
    settings = to_settings(ps)
    term = settings.target_term
    manual = [{**manual_out(ms), "section": ms.section, "virtual": ms.virtual,
               "projected": _manual_projection(res, ms.code, ms.virtual)} for ms in manual_sections_for(db, term)]
    master, added, manual_stale = eng.add_manual_sections(res["master"], manual, res["profiles"])
    ovr = overrides_for(db, term)
    master, applied = eng.apply_overrides(master, ovr, res["profiles"])
    # Deleted sections (and recitations tied to a deleted lecture) leave the schedule
    master, removed_rows = eng.remove_sections(master, [sid for sid in applied if ovr[sid].get("removed")])
    removed_groups: dict[tuple[int, bool], int] = {}
    for r in removed_rows:
        if r["component"] == "Lecture":
            g = (r["code"], r["virtual"])
            removed_groups[g] = removed_groups.get(g, 0) + 1
    manual_codes = {m["code"] for m in manual if m["section_id"] in added}
    # Courses whose seats changed (raised caps or hand-added sections): re-spread their projected
    # students and re-check the half-full overflow against the seats now on the schedule
    changed_ids = set(added) | {sid for sid in applied if ovr[sid].get("cap")}
    rows = master[master["Section ID"].isin(changed_ids)] if not master.empty else master
    edited_groups = {(int(c.split()[1]), str(mod).startswith("Online")) for c, mod in zip(rows.get("Course", []), rows.get("Modality", []))}
    edited_groups |= set(removed_groups)
    master = eng.rebalance_projection(master, res["demand"], edited_groups)
    gaps = eng.capacity_gaps(master, res.get("unseated"), res["demand"], removed_groups)
    conflicts = eng.detect_conflicts(master, res["profiles"], settings, res["prereq"], res["dropped"],
                                     res["pref_warnings"], gaps, manual_codes)
    workload = eng.workload_summary(master, res["profiles"], settings)
    edited = list(dict.fromkeys(applied + added))      # Manual Edit badge: overrides and hand-added sections
    return {**res, "master": master, "conflicts": conflicts, "workload": workload,
            "overrides_applied": edited, "manual_sections": added,
            "capacity_gaps": gaps, "edited_groups": edited_groups, "removed_sections": removed_rows,
            "overrides_stale": sorted((set(ovr) - set(applied)) | set(manual_stale))}


def suggest_section(db: Session, ps, code: int, instructor: str | None, exclude_id: str | None) -> dict:
    """Best lecture blocks for an extra section of `code`, judged against the current edited schedule."""
    res = schedule(db, ps)
    popularity = eng.slot_popularity(res["enrollment"])
    name = instructor if instructor and instructor != eng.UNSTAFFED else None
    return {"blocks": eng.suggest_time_blocks(res["master"], code, name, popularity, exclude_id),
            "volunteers": eng.likely_volunteers(code, res["profiles"], res["master"])}


def demand_with_edits(db: Session, ps) -> tuple[dict, pd.DataFrame]:
    """The forecast, with section caps / seats / seat fill updated for courses edited on the schedule."""
    res = run_plan(db, ps)
    sch = schedule(db, ps)
    d, m = res["demand"].copy(), sch["master"]
    d["_caps"] = d["_caps"].astype(object)
    for code, virtual in sch["edited_groups"]:
        idx = d.index[(d["_code"] == code) & (d["_virtual"] == virtual)]
        if not len(idx):
            continue
        i = idx[0]
        caps = m.loc[eng._group_mask(m, code, virtual), "Section Cap"].astype(int).tolist()
        proj, seats = int(d.at[i, "Projected Enrollment"]), int(sum(caps))
        remaining = max(0, proj - seats)
        d.at[i, "_caps"] = caps
        d.at[i, "_unseated"] = remaining
        d.at[i, "Planned Sections"] = len(caps)
        d.at[i, "Section Caps"] = ", ".join(str(c) for c in caps) if caps else "—"
        d.at[i, "Seats Offered"] = seats
        d.at[i, "Seat Fill %"] = proj / seats if seats else 0.0
        notes = [n for n in str(d.at[i, "Notes"] or "").split("; ") if n and "over capacity" not in n]
        notes.append("Includes manual schedule edits")
        if remaining:
            notes.append(f"{remaining} student{'s' if remaining != 1 else ''} over capacity")
        d.at[i, "Notes"] = "; ".join(notes)
    return res, d


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
