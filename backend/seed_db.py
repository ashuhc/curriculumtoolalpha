"""
seed_db.py — populate the database from the legacy prototype files.

    python seed_db.py            # create tables; seed any table that is still empty
    python seed_db.py --reset    # DROP everything (incl. web submissions & overrides) and re-seed

Sources (repository root, or $SCHEDULER_DATA_DIR):
    ECON_Enrollment.xlsx      -> enrollment_records
    TEACHER_PREFERENCES.py    -> courses (COURSE_DATABASE + COURSE_DESCRIPTIONS, parsed with ast)
    custom_courses.json       -> courses (overrides the above when present)
    custom_faculty.json       -> faculty
    faculty_overloads.json    -> overloads
    teacher_preferences.csv   -> preference_submissions
    (env)                     -> users: an admin account (ADMIN_EMAIL / ADMIN_PASSWORD) and, unless
                                 SEED_DEMO_USERS=false, demo accounts for trying collaboration
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from datetime import datetime

import pandas as pd

import engine as eng
from database import Base, SessionLocal, engine as db_engine
from auth import hash_password
from models import Course, EnrollmentRecord, Faculty, Overload, PreferenceSubmission, ScheduleOverride, User


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _prefs_app_literals() -> tuple[dict, dict]:
    """Extract COURSE_DATABASE and COURSE_DESCRIPTIONS from TEACHER_PREFERENCES.py without running it."""
    found = {"COURSE_DATABASE": {}, "COURSE_DESCRIPTIONS": {}}
    try:
        with open(eng.PREFS_APP_FILE) as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id in found:
                        found[t.id] = ast.literal_eval(node.value)
    except (OSError, SyntaxError, ValueError) as e:
        print(f"  ! could not parse TEACHER_PREFERENCES.py: {e}")
    return found["COURSE_DATABASE"], found["COURSE_DESCRIPTIONS"]


def seed_enrollment(db) -> pd.DataFrame:
    raw = pd.read_excel(eng.ENROLLMENT_FILE)
    missing = eng.validate_enrollment_columns(raw)
    if missing:
        sys.exit(f"ECON_Enrollment.xlsx is missing columns: {missing}")
    if db.query(EnrollmentRecord).count():
        print("  · enrollment_records already populated — skipped")
        return raw
    db.add_all(EnrollmentRecord(**r) for r in records_from_frame(raw))
    print(f"  ✓ {len(raw)} enrollment records")
    return raw


def records_from_frame(raw: pd.DataFrame) -> list[dict]:
    """Map enrollment spreadsheet rows onto EnrollmentRecord columns (shared with the upload API)."""
    def num(v):
        return None if pd.isna(v) else float(v)

    out = []
    for _, r in raw.iterrows():
        code = pd.to_numeric(r["Course #"], errors="coerce")
        if pd.isna(code):
            continue
        crn = pd.to_numeric(r.get("CRN"), errors="coerce")
        out.append(dict(
            academic_period=str(r["ACADEMIC_PERIOD_DESC"]), campus=str(r.get("CAMPUS", "") or ""),
            course_number=int(code), course_title=str(r.get("Course Title", "") or ""),
            crn=None if pd.isna(crn) else int(crn),
            instructional_method=str(r.get("Instructional Method", "") or ""),
            instructor="" if pd.isna(r.get("Instructor")) else str(r["Instructor"]).strip(),
            schedule="" if pd.isna(r.get("Schedule")) else str(r["Schedule"]),
            maximum_enrollment=num(r.get("MAXIMUM_ENROLLMENT")), ug_enrollment=num(r.get("UG_ENROLLMENT")),
        ))
    return out


def seed_courses(db, raw: pd.DataFrame):
    if db.query(Course).count():
        print("  · courses already populated — skipped")
        return
    database, descriptions = _prefs_app_literals()
    custom = _load_json(eng.COURSES_FILE, None)
    if custom:
        database = custom
    rows: dict[int, Course] = {}
    for key, val in database.items():
        codes = eng.extract_codes(key)
        if not codes or codes[0] >= 5000:
            continue
        title = val.get("title", "") if isinstance(val, dict) else str(val)
        desc = descriptions.get(key, {}).get("description", "") if isinstance(descriptions.get(key), dict) else ""
        if isinstance(val, dict):
            desc = val.get("description", desc)
        rows[codes[0]] = Course(code=codes[0], title=title, description=desc, active=True)
    # Undergraduate courses that appear in enrollment history but not in the form's catalog
    hist = raw[pd.to_numeric(raw["Course #"], errors="coerce") < 5000]
    for code, title in hist.groupby("Course #")["Course Title"].last().items():
        code = int(code)
        if code not in rows:
            rows[code] = Course(code=code, title=str(title), description="(added from enrollment history)")
    db.add_all(rows.values())
    print(f"  ✓ {len(rows)} undergraduate courses")


def seed_faculty(db) -> dict[str, Faculty]:
    existing = {f.name: f for f in db.query(Faculty).all()}
    if existing:
        print("  · faculty already populated — skipped")
        return existing
    names = [n for n in _load_json(eng.FACULTY_FILE, []) if n and n != "Select your name..."]
    roster = _load_json(eng.ROSTER_FILE, {})       # optional confirmed groups from the Streamlit roster tab
    out = {}
    for n in names:
        saved = roster.get(n, {})
        out[n] = Faculty(name=n, faculty_type=saved.get("type"), annual_reduction=saved.get("reduction"))
    db.add_all(out.values())
    db.flush()
    print(f"  ✓ {len(out)} faculty")
    return out


def seed_overloads(db, faculty: dict[str, Faculty]):
    if db.query(Overload).count():
        print("  · overloads already populated — skipped")
        return
    data = _load_json(eng.OVERLOADS_FILE, {})
    n = 0
    for name, v in data.items():
        f = faculty.get(name)
        if f is None:
            continue
        sem = str(v.get("semester", "None")).title()
        db.add(Overload(faculty_id=f.id, overloading=bool(v.get("overloading")),
                        semester=sem if sem in ("None", "Fall", "Spring", "Both") else "None"))
        n += 1
    print(f"  ✓ {n} overload records")


def seed_preferences(db, faculty: dict[str, Faculty]):
    if db.query(PreferenceSubmission).count():
        print("  · preference_submissions already populated — skipped")
        return
    try:
        df = pd.read_csv(eng.PREFERENCES_FILE)
    except (OSError, pd.errors.EmptyDataError):
        df = pd.DataFrame()
    n = 0
    for _, r in df.iterrows():
        name = str(r.get("Full Name", "")).strip()
        if not name or name.lower() in ("nan", "select your name..."):
            continue
        f = faculty.get(name)
        if f is None:                      # submitter missing from the roster: add them
            f = Faculty(name=name)
            db.add(f)
            db.flush()
            faculty[name] = f
        ranks = []
        for i in range(1, 7):
            for c in eng.extract_codes(r.get(f"Rank {i} Course")):
                if c < 5000 and c not in ranks:
                    ranks.append(c)
        overload = str(r.get("Course Overload", r.get("Course Overload Interest", "No"))).strip().lower() in (
            "yes", "true", "1", "y")
        sem = str(r.get("Overload Semester", "None")).title() if overload else "None"
        ts = pd.to_datetime(r.get("Timestamp"), errors="coerce")
        circ = str(r.get("Unique Circumstances", "") or "")
        db.add(PreferenceSubmission(
            faculty_id=f.id, submitted_at=ts.to_pydatetime() if not pd.isna(ts) else datetime.utcnow(),
            email=str(r.get("Email", "") or ""),
            principles=[c for c in eng.extract_codes(r.get("Principles Preferences")) if c in (1115, 1116)],
            ranks=ranks[:6], fall_target=eng.safe_int(r.get("Fall Desired Courses"), 2),
            spring_target=eng.safe_int(r.get("Spring Desired Courses"), 2), overload=overload,
            overload_semester=sem if sem in ("Fall", "Spring", "Both") else ("Both" if overload else "None"),
            unique_circumstances="" if circ.lower() in ("none", "nan") else circ,
        ))
        if not f.email and str(r.get("Email", "")) not in ("", "nan"):
            f.email = str(r["Email"])
        n += 1
    print(f"  ✓ {n} preference submissions" + ("" if n else " (teacher_preferences.csv has no responses yet)"))


def seed_users(db, faculty: dict[str, Faculty]):
    if db.query(User).count():
        print("  · users already populated — skipped")
        return
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@northeastern.edu").lower()
    admin_pw = os.environ.get("ADMIN_PASSWORD", "econpassword123")
    accounts = [("Department Scheduler", admin_email, admin_pw, "admin", None)]
    if os.environ.get("SEED_DEMO_USERS", "true").lower() != "false":
        stone = faculty.get("Stone, Michael")
        accounts += [
            ("Associate Scheduler", "scheduler2@northeastern.edu", "scheduler123", "admin", None),
            ("Michael Stone", "m.stone@northeastern.edu", "faculty123", "faculty", stone.id if stone else None),
        ]
    for name, email, pw, role, fid in accounts:
        db.add(User(name=name, email=email, role=role, password_hash=hash_password(pw), faculty_id=fid))
        print(f"  ✓ user {email} ({role})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="drop all tables before seeding")
    args = ap.parse_args()

    import models  # noqa: F401
    if args.reset:
        print("Dropping all tables…")
        Base.metadata.drop_all(bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    print(f"Seeding {db_engine.url} from {eng.BASE_DIR}")
    with SessionLocal() as db:
        raw = seed_enrollment(db)
        seed_courses(db, raw)
        faculty = seed_faculty(db)
        seed_overloads(db, faculty)
        seed_preferences(db, faculty)
        seed_users(db, faculty)
        db.commit()
        print(f"Done. {db.query(ScheduleOverride).count()} schedule overrides on file.")


if __name__ == "__main__":
    main()
