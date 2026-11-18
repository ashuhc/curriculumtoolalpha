"""
engine.py
=========
Planning engine for the Northeastern University Department of Economics
Automated Course Scheduler. Framework-free: the FastAPI backend (main.py)
feeds it data from the database, and the legacy Streamlit prototype
(../COURSE_SCHEDULER.py, via ../scheduler_engine.py) feeds it the raw files.

Pipeline
--------
Demand estimation & section planning
    load_enrollment()        clean ECON_Enrollment.xlsx, impute missing counts
    estimate_demand()        project per-course demand for a target term
    plan_sections()          turn demand into lecture + recitation sections
    validate_prerequisites() check level rules and prerequisite availability

Instructor matching, time slots & conflicts
    load_preferences()       ingest teacher_preferences.csv (TEACHER_PREFERENCES.py)
    build_faculty_profiles() roster type, targets, overloads, willingness scores
    assign_instructors()     core-first greedy preference matching
    assign_time_slots()      Course_Sequences.pdf sequence assignment
    finalize_master()        derive meeting days/times (also after manual edits)
    detect_conflicts()       unresolved-conflicts report
    workload_summary()       per-faculty load vs. contract + overloads

    apply_overrides()        layer manual instructor/sequence edits on top

`run_pipeline()` chains everything and returns a dict of DataFrames. Every
input can be injected (DB-backed) or left as None to read the legacy files.
"""

from __future__ import annotations

import ast
import json
import math
import os
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ==============================================================================
# 0. FILE LOCATIONS
# ==============================================================================
# Legacy data files live in the repository root (one level above /backend).
BASE_DIR = os.environ.get(
    "SCHEDULER_DATA_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _path(name: str) -> str:
    return os.path.join(BASE_DIR, name)


ENROLLMENT_FILE = _path("ECON_Enrollment.xlsx")
PREFERENCES_FILE = _path("teacher_preferences.csv")
OVERLOADS_FILE = _path("faculty_overloads.json")
FACULTY_FILE = _path("custom_faculty.json")
ROSTER_FILE = _path("faculty_roster.json")
COURSES_FILE = _path("custom_courses.json")
PREFS_APP_FILE = _path("TEACHER_PREFERENCES.py")

REQUIRED_ENROLLMENT_COLUMNS = [
    "ACADEMIC_PERIOD_DESC", "CAMPUS", "Course #", "Course Title",
    "Instructional Method", "Instructor", "Schedule",
    "MAXIMUM_ENROLLMENT", "UG_ENROLLMENT",
]

# ==============================================================================
# 1. CURRICULUM DEFINITIONS
# ==============================================================================
ECON_AT_NU = 1000
PRINCIPLES = [1115, 1116, 2350]      # Macro, Micro, Statistics
FOLLOW_UPS = [2315, 2316, 2560]      # Macro theory, Micro theory, Econometrics
CAPSTONES = [4692, 4997]             # Senior Seminar, Senior Thesis
MANDATORY_CORE = [ECON_AT_NU] + PRINCIPLES + FOLLOW_UPS + CAPSTONES

# Recitation course -> the lecture it supports
RECITATION_FOR = {1125: 1115, 1126: 1116}
RECITATION_OF = {v: k for k, v in RECITATION_FOR.items()}

# Principles lectures are run as a mix of large lectures + small sections
LARGE_LECTURE_COURSES = {1115, 1116}

# Placeholder / arranged / independent courses never get a scheduled section
NON_SCHEDULED = {1990, 2990, 3990, 4990, 4965, 4970, 4971, 4991, 4992, 4994, 4996}

# Core courses students take in the same stage; overlapping them is penalised
CORE_STAGE = {
    1000: "Foundations", 1115: "Foundations", 1116: "Foundations",
    2350: "Intermediate", 2315: "Intermediate", 2316: "Intermediate", 2560: "Intermediate",
    4692: "Capstone", 4997: "Capstone",
}

THEORY = {2315, 2316}
PRINCIPLES_LECTURES = {1115, 1116}

# Explicit prerequisite overrides. Each inner list is an "any of" group; all
# groups are required. Courses not listed fall back to level-based defaults.
PREREQUISITE_OVERRIDES = {
    2315: [[1115], [1116]],
    2316: [[1115], [1116]],
    2350: [[1115, 1116]],
    2560: [[2350]],
    4692: [[2315], [2316], [2560]],
    4997: [[2315], [2316], [2560]],
}

# Faculty groups -> annual course load (min, standard, max). None = no contract.
TENURED = "Tenured Track / Tenured"
FACULTY_TYPES = {
    TENURED: {"min": 0, "standard": 3, "max": 3},
    "Full-Time Teaching": {"min": 6, "standard": 6, "max": 6},
    "Temporary": {"min": 6, "standard": 6, "max": 6},
    "Adjunct": {"min": 1, "standard": 2, "max": 2},
    "Recitation Leader": None,
}

# Older labels still found in saved rosters / databases
LEGACY_FACULTY_TYPES = {"Tenured": TENURED}


def normalize_faculty_type(name):
    """Map a legacy group label (e.g. "Tenured") to its current name."""
    return LEGACY_FACULTY_TYPES.get(name, name)


VIRTUAL_CAP_LIMIT = 25


# ==============================================================================
# 2. COURSE SEQUENCES (Course_Sequences.pdf, Fall 2011 and after)
# ==============================================================================
def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _blocks(days: str, start: str, end: str):
    return [(d, _mins(start), _mins(end)) for d in days]


# Sequences 1-5 and A-H are for classes only (6 and 7 are administrative).
CLASS_SEQUENCES = {
    "1": _blocks("MWR", "08:00", "09:05"),
    "2": _blocks("MWR", "09:15", "10:20"),
    "3": _blocks("MWR", "10:30", "11:35"),
    "4": _blocks("MWR", "13:35", "14:40"),
    "5": _blocks("MWR", "16:35", "17:40"),
    "A": _blocks("MR", "11:45", "13:25"),
    "B": _blocks("MW", "14:50", "16:30"),
    "C": _blocks("TF", "08:00", "09:40"),
    "D": _blocks("TF", "09:50", "11:30"),
    "E": _blocks("WF", "11:45", "13:25"),
    "F": _blocks("TF", "13:35", "15:15"),
    "G": _blocks("TF", "15:25", "17:05"),
    "H": _blocks("T", "11:45", "13:25") + _blocks("R", "14:50", "16:30"),
}

# Sequences L-W are for laboratory or studio instruction.
LAB_SEQUENCES = {
    "L": _blocks("MWR", "08:00", "11:30"),
    "P": _blocks("MWR", "08:00", "10:20"),
    "Q": _blocks("MWR", "10:30", "13:25"),
    "M": _blocks("MWR", "11:45", "14:40"),
    "S": _blocks("MWR", "13:35", "16:30"),
    "N": _blocks("MWR", "14:50", "17:40"),
    "R": _blocks("MWR", "13:35", "17:40"),
    "T": _blocks("TF", "08:00", "11:30"),
    "U": _blocks("TF", "11:45", "15:15"),
    "W": _blocks("TF", "13:35", "17:05"),
    "V": _blocks("TF", "15:25", "17:25"),
}


def _build_recitation_slots():
    """
    Recitations meet once a week for 65 minutes inside a lab sequence window.
    Slot code = <lab sequence>-<day><start>, e.g. "N-W1450" = Wed 2:50-3:55 PM.
    """
    mwr = [("P", "08:00"), ("P", "09:15"), ("Q", "10:30"), ("M", "11:45"),
           ("S", "13:35"), ("N", "14:50"), ("N", "16:35")]
    tf = [("T", "08:00"), ("T", "09:50"), ("U", "11:45"), ("W", "13:35"), ("V", "15:25")]
    slots = {}
    for days, starts in (("MWR", mwr), ("TF", tf)):
        for day in days:
            for lab, start in starts:
                s = _mins(start)
                code = f"{lab}-{day}{start.replace(':', '')}"
                slots[code] = [(day, s, s + 65)]
    return slots


RECITATION_SLOTS = _build_recitation_slots()
ALL_SLOTS = {**CLASS_SEQUENCES, **LAB_SEQUENCES, **RECITATION_SLOTS}
ASYNC_SLOT = "ASYNC"
UNSCHEDULED = "UNSCHEDULED"
UNSTAFFED = "UNSTAFFED"
RECITATION_TBA = "TBA (Recitation Leader)"
DAY_ORDER = "MTWRF"


def fmt_time(m: int) -> str:
    h, mm = divmod(int(m), 60)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{mm:02d} {suffix}"


def describe_slot(code: str):
    """Return (days, time text) for a slot code."""
    if code == ASYNC_SLOT:
        return "—", "Asynchronous (no meeting time)"
    blocks = ALL_SLOTS.get(code)
    if not blocks:
        return "—", "Not scheduled"
    # Group days that share the same time window
    windows: dict[tuple[int, int], str] = {}
    for d, s, e in blocks:
        windows[(s, e)] = windows.get((s, e), "") + d
    days = "".join(sorted({d for d, _, _ in blocks}, key=DAY_ORDER.index))
    parts = [f"{''.join(sorted(ds, key=DAY_ORDER.index))} {fmt_time(s)}–{fmt_time(e)}"
             for (s, e), ds in sorted(windows.items(), key=lambda kv: DAY_ORDER.index(kv[1][0]))]
    return days, "; ".join(parts)


def slot_type(code: str) -> str:
    if code in CLASS_SEQUENCES:
        return "Class sequence"
    if code in LAB_SEQUENCES:
        return "Lab/studio sequence"
    if code in RECITATION_SLOTS:
        return "Recitation (lab window)"
    if code == ASYNC_SLOT:
        return "Online / async"
    return "—"


def blocks_overlap(a, b) -> bool:
    for d1, s1, e1 in a:
        for d2, s2, e2 in b:
            if d1 == d2 and s1 < e2 and s2 < e1:
                return True
    return False


def slots_overlap(code_a: str, code_b: str) -> bool:
    a, b = ALL_SLOTS.get(code_a), ALL_SLOTS.get(code_b)
    return bool(a and b and blocks_overlap(a, b))


def parse_schedule(text) -> list:
    """Parse a historical schedule string like 'T 1145-1325, R 1450-1630'."""
    blocks = []
    for part in str(text).split(","):
        m = re.match(r"\s*([MTWRF]+)\s+(\d{4})-(\d{4})", part)
        if not m:
            continue
        days, s, e = m.groups()
        s_m = int(s[:2]) * 60 + int(s[2:])
        e_m = int(e[:2]) * 60 + int(e[2:])
        blocks += [(d, s_m, e_m) for d in days]
    return blocks


def match_class_sequence(text):
    """Map a historical meeting pattern onto a class sequence code (or None)."""
    blocks = parse_schedule(text)
    if not blocks:
        return None
    key = sorted((d, s) for d, s, _ in blocks)
    for code, seq in CLASS_SEQUENCES.items():
        ref = sorted((d, s) for d, s, _ in seq)
        if len(ref) == len(key) and all(a[0] == b[0] and abs(a[1] - b[1]) <= 10 for a, b in zip(ref, key)):
            return code
    return None


# ==============================================================================
# 3. SMALL HELPERS
# ==============================================================================
def course_level(code: int) -> int:
    return (int(code) // 1000) * 1000


def course_category(code: int) -> str:
    if code in RECITATION_FOR:
        return "Recitation"
    if code in CAPSTONES:
        return "Core · Capstone"
    if code == ECON_AT_NU:
        return "Core · Econ at NU"
    if code in PRINCIPLES:
        return "Core · Principles"
    if code in FOLLOW_UPS:
        return "Core · Follow-up"
    return "Elective"


def is_core(code: int) -> bool:
    return code in MANDATORY_CORE or code in RECITATION_FOR


def extract_codes(value) -> list[int]:
    """Pull 4-digit course numbers out of strings like 'ECON 3424 - Law and Economics'."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    return [int(c) for c in re.findall(r"\b(\d{4})\b", str(value))]


def safe_int(value, default=None):
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_term_label(label: str):
    """'Fall 2026' / 'Fall 2026 Semester' -> ('Fall', 2026). Returns (None, None) if invalid."""
    m = re.search(r"(Fall|Spring)\s+(\d{4})", str(label), flags=re.IGNORECASE)
    if not m:
        return None, None
    return m.group(1).title(), int(m.group(2))


def term_ordinal(sem: str, year: int) -> int:
    # Spring Y precedes Fall Y; consecutive terms differ by 1.
    return year * 2 + (1 if sem == "Fall" else 0)


def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    return default


# ==============================================================================
# 4. COURSE CATALOG & PREREQUISITES
# ==============================================================================
def load_catalog(enrollment: pd.DataFrame | None = None) -> dict[int, str]:
    """
    Course titles. Uses the admin-edited custom_courses.json when present,
    otherwise reads COURSE_DATABASE straight out of TEACHER_PREFERENCES.py
    (parsed with `ast`, so the form's Streamlit code never executes).
    Titles from the enrollment file fill any gaps.
    """
    raw = _load_json(COURSES_FILE, None)
    if raw is None and os.path.exists(PREFS_APP_FILE):
        try:
            with open(PREFS_APP_FILE, "r") as f:
                tree = ast.parse(f.read())
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "COURSE_DATABASE" for t in node.targets
                ):
                    raw = ast.literal_eval(node.value)
                    break
        except (OSError, SyntaxError, ValueError):
            raw = None
    catalog: dict[int, str] = {}
    for key, val in (raw or {}).items():
        codes = extract_codes(key)
        if not codes:
            continue
        title = val.get("title", "") if isinstance(val, dict) else str(val)
        catalog[codes[0]] = title
    if enrollment is not None and not enrollment.empty:
        latest = enrollment.sort_values("ordinal").groupby("course")["title"].last()
        for code, title in latest.items():
            catalog.setdefault(int(code), str(title))
    return {c: t for c, t in catalog.items() if c < 5000}


def get_prerequisites(code: int) -> list[list[int]]:
    if code in PREREQUISITE_OVERRIDES:
        return PREREQUISITE_OVERRIDES[code]
    if code in RECITATION_FOR:
        return []  # co-requisite of its lecture, not a prerequisite chain
    level = course_level(code)
    if level == 1000:
        return []
    if level == 2000:
        return [[1115, 1116]]
    if level == 3000:
        return [[1115], [1116]]           # requires the principles courses
    if level == 4000:
        return [[2315], [2316]]           # multiple prerequisites incl. theory
    return []


def format_prereqs(groups) -> str:
    if not groups:
        return "None"
    return " AND ".join(
        "ECON " + str(g[0]) if len(g) == 1 else "(" + " or ".join(f"ECON {c}" for c in g) + ")"
        for g in groups
    )


def validate_prerequisites(offered_codes: set[int], catalog: dict[int, str]) -> pd.DataFrame:
    """
    Strict prerequisite checks for every offered course:
      * 1000-level: no prerequisites allowed
      * 3000-level: must require the principles courses
      * 4000-level: must require multiple prerequisites including theory
      * every prerequisite group must have at least one course offered this term
        (so the pathway into the course is open to students)
    """
    rows = []
    for code in sorted(offered_codes):
        if code in RECITATION_FOR:
            continue
        groups = get_prerequisites(code)
        flat = {c for g in groups for c in g}
        level = course_level(code)
        rule_ok, rule_msg = True, "OK"
        if level == 1000 and groups:
            rule_ok, rule_msg = False, "1000-level courses must not have prerequisites"
        elif level == 3000 and not flat & PRINCIPLES_LECTURES:
            rule_ok, rule_msg = False, "3000-level courses must require principles"
        elif level == 4000 and (len(groups) < 2 or not flat & THEORY):
            rule_ok, rule_msg = False, "4000-level courses need multiple prerequisites incl. theory"
        missing = [g for g in groups if not any(c in offered_codes for c in g)]
        rows.append({
            "Course": f"ECON {code}",
            "Title": catalog.get(code, ""),
            "Level": level,
            "Prerequisites": format_prereqs(groups),
            "Level Rule": "✅ " + rule_msg if rule_ok else "❌ " + rule_msg,
            "Pathway Offered This Term": "✅ Yes" if not missing else "⚠️ Missing " + format_prereqs(missing),
            "_ok": rule_ok and not missing,
        })
    return pd.DataFrame(rows)


# ==============================================================================
# ENROLLMENT LOADING & DEMAND ESTIMATION
# ==============================================================================
def validate_enrollment_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in REQUIRED_ENROLLMENT_COLUMNS if c not in df.columns]


def load_enrollment(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise the raw enrollment export:
      * keep Fall/Spring undergraduate (<5000) rows, drop One-On-One/arranged
      * flag online/virtual sections
      * impute missing UG_ENROLLMENT as cap x the course's median fill rate
        (missing counts otherwise make demand look artificially low)
    """
    missing = validate_enrollment_columns(raw)
    if missing:
        raise ValueError(f"Enrollment data is missing required columns: {', '.join(missing)}")

    df = raw.copy()
    df["course"] = pd.to_numeric(df["Course #"], errors="coerce")
    df = df[df["course"].notna()].copy()
    df["course"] = df["course"].astype(int)

    parsed = df["ACADEMIC_PERIOD_DESC"].apply(parse_term_label)
    df["sem"] = parsed.str[0]
    df["year"] = parsed.str[1]
    df = df[df["sem"].notna()].copy()
    df["year"] = df["year"].astype(int)
    df["term"] = df["sem"] + " " + df["year"].astype(str)
    df["ordinal"] = [term_ordinal(s, y) for s, y in zip(df["sem"], df["year"])]

    df["is_grad"] = df["course"] >= 5000
    method = df["Instructional Method"].astype(str)
    df["virtual"] = (df["CAMPUS"].astype(str).str.upper() == "VTL") | method.str.contains(
        "Online|Virtual", case=False, na=False)
    df["arranged"] = method.str.contains("One-On-One", case=False, na=False)
    df["title"] = df["Course Title"].astype(str)
    df["instructor"] = df["Instructor"].fillna("").astype(str).str.strip()

    df["max_enr"] = pd.to_numeric(df["MAXIMUM_ENROLLMENT"], errors="coerce")
    df["ug_raw"] = pd.to_numeric(df["UG_ENROLLMENT"], errors="coerce")
    df["max_enr"] = df["max_enr"].fillna(df["ug_raw"])

    fill = (df["ug_raw"] / df["max_enr"]).where(df["max_enr"] > 0)
    course_fill = fill.groupby(df["course"]).median().clip(upper=1.0)
    df["ug_imputed"] = df["ug_raw"].isna() & df["max_enr"].notna()
    df["ug_enr"] = df["ug_raw"]
    df.loc[df["ug_imputed"], "ug_enr"] = (
        df.loc[df["ug_imputed"], "max_enr"] * df.loc[df["ug_imputed"], "course"].map(course_fill).fillna(0.9)
    ).round()
    df = df[df["ug_enr"].notna()].copy()

    df["seq"] = df["Schedule"].apply(match_class_sequence)
    return df.reset_index(drop=True)


@dataclass
class Settings:
    target_term: str = "Spring 2027"
    growth_multiplier: float = 1.0
    history_window: int = 3            # same-type terms used for the projection
    apply_trend: bool = True
    max_annual_trend: float = 0.10     # clip historical trend to +/-10%/yr
    large_lecture_cap: int = 200
    small_section_cap: int = 45
    virtual_cap: int = 25
    recitation_cap: int = 30
    min_elective_demand: int = 15
    default_elective_demand: int = 40
    history_fallback: bool = True      # infer prefs from teaching history if no form
    force_fill_core: bool = False      # assign any free faculty to unstaffed core
    recitation_leader_load: int = 5    # default recitations per leader per term

    @property
    def target(self):
        return parse_term_label(self.target_term)


def _large_lecture_count(code: int, virtual: bool, projected: int, s: Settings) -> int:
    """Number of large-lecture sections (s.large_lecture_cap seats) planned for a course.
    Large lectures run while at least 75% of a lecture's seats would still be filled."""
    if virtual or code not in LARGE_LECTURE_COURSES or projected <= 0:
        return 0
    n, remaining = 0, projected
    while remaining >= 0.75 * s.large_lecture_cap:
        n += 1
        remaining -= s.large_lecture_cap
    return n


HALF_FULL = 0.5        # an additional section opens only if it would be at least half full
OVER_CAP_TOLERANCE = 0.10


def _sections_needed(students: int, cap: int) -> int:
    """Full sections, plus one more only if the overflow fills at least half of it."""
    if students <= 0 or cap <= 0:
        return 0
    full, rem = divmod(students, cap)
    return full + (1 if rem >= HALF_FULL * cap else 0)


def _uniform_sections(students: int, cap: int, tolerance: float = OVER_CAP_TOLERANCE, at_least_one=True) -> tuple[int, int]:
    """
    (sections, cap) for `students` in sections of a standard `cap`. A small overflow is first
    absorbed by raising caps up to `tolerance`; an extra section is added only when the
    overflow can't be absorbed AND would leave that section at least half full.
    """
    if students <= 0:
        return 0, cap
    n_absorb = math.ceil(students / (cap * (1 + tolerance)))      # fewest sections within tolerance
    n = min(n_absorb, _sections_needed(students, cap))
    n = max(1, n) if at_least_one else n
    if n and students > n * cap:
        cap = min(math.ceil(students / n), int(math.floor(cap * (1 + tolerance))))
    return n, cap


def _section_caps_for(code: int, virtual: bool, projected: int, hist_cap: float, s: Settings) -> tuple[list[int], int]:
    """
    Section capacities for `projected` students, and how many students they can't seat.

    Half-full rule: the first section of a course is planned whenever the course runs
    (electives also need min_elective_demand), but every *additional* section needs at
    least 50% of a standard section's seats. Smaller overflows are absorbed up to 10%
    over cap (in-person) and otherwise reported as unseated demand instead of opening
    a sparse section. Large Principles lectures keep their own 75%-full rule. This never
    plans more sections than the plain 10%-tolerance rule would.
    """
    if projected <= 0:
        return [], 0
    if virtual:
        cap = int(min(hist_cap or s.virtual_cap, s.virtual_cap, VIRTUAL_CAP_LIMIT))
        n, cap = _uniform_sections(projected, cap, tolerance=0.0)   # remote caps are hard limits
        return [cap] * n, max(0, projected - n * cap)
    if code in LARGE_LECTURE_COURSES:
        # Large lectures (100-200+) while demand supports them, rest in small sections
        n_large = _large_lecture_count(code, virtual, projected, s)
        caps = [s.large_lecture_cap] * n_large
        remaining = projected - n_large * s.large_lecture_cap
        if remaining > 0:
            n_small, small_cap = _uniform_sections(remaining, s.small_section_cap, at_least_one=(n_large == 0))
            caps += [small_cap] * n_small
        return caps, max(0, projected - sum(caps))
    if hist_cap and not math.isnan(hist_cap):
        cap = int(round(hist_cap))
    elif code in CAPSTONES:
        cap = 20
    else:
        cap = s.small_section_cap
    cap = int(min(max(cap, 15), s.large_lecture_cap))
    # e.g. 44 students & a 40-seat cap -> one 44-seat section; 60 & 45 -> one 49-seat section
    # (11 unseated) because a second section would hold fewer than 23 students.
    n, cap = _uniform_sections(projected, cap)
    return [cap] * n, max(0, projected - n * cap)


def estimate_demand(enr: pd.DataFrame, settings: Settings, catalog: dict[int, str],
                    requested_electives: set[int] | None = None) -> pd.DataFrame:
    """
    Project student demand per (course, modality) for the target term using
    prior same-semester-type terms:
        projected = recency-weighted mean
                    x (1 + clipped annual trend) ^ (years ahead of history centroid)
                    x growth multiplier
    Rows also carry the planned section capacities (`_caps`) used by plan_sections().
    """
    sem, year = settings.target
    if sem is None:
        raise ValueError(f"Could not parse target term '{settings.target_term}'. Use e.g. 'Fall 2027'.")
    target_ord = term_ordinal(sem, year)
    requested_electives = {c for c in (requested_electives or set())
                           if c < 5000 and c not in NON_SCHEDULED and c not in RECITATION_FOR}

    ug = enr[(~enr["is_grad"]) & (~enr["arranged"]) & (~enr["course"].isin(NON_SCHEDULED))
             & (~enr["course"].isin(RECITATION_FOR))]
    prior = ug[ug["ordinal"] < target_ord]
    same_type = prior[prior["sem"] == sem]
    actual = ug[ug["ordinal"] == target_ord]

    per_term = (same_type.groupby(["course", "virtual", "ordinal", "year"])
                .agg(students=("ug_enr", "sum"), sections=("ug_enr", "size"),
                     cap=("max_enr", "median"))
                .reset_index())
    # Typical section cap: same-semester history first (Fall vs Spring sizes differ), else any term
    recent = prior[prior["ordinal"] >= target_ord - 8]
    hist_cap = recent.groupby(["course", "virtual"])["max_enr"].median()
    hist_cap.update(recent[recent["sem"] == sem].groupby(["course", "virtual"])["max_enr"].median())

    recent_cutoff = target_ord - 6           # "recently offered" = last ~3 years
    same_type_terms = sorted(same_type["ordinal"].unique())
    last_two_same = set(same_type_terms[-2:])

    candidates: set[tuple[int, bool]] = set()
    for (code, virt), g in per_term.groupby(["course", "virtual"]):
        if virt:
            if set(g["ordinal"]) & last_two_same:
                candidates.add((code, True))
        elif code in MANDATORY_CORE or g["ordinal"].max() >= recent_cutoff:
            candidates.add((code, False))
    candidates |= {(c, False) for c in MANDATORY_CORE}
    candidates |= {(c, False) for c in requested_electives}

    rows = []
    for code, virt in sorted(candidates):
        g = per_term[(per_term["course"] == code) & (per_term["virtual"] == virt)].sort_values("ordinal")
        g = g.tail(settings.history_window)
        notes = []
        if g.empty:
            # No same-semester history: fall back to any-term history, then a default
            anyg = (prior[(prior["course"] == code) & (prior["virtual"] == virt)]
                    .groupby("ordinal")["ug_enr"].sum())
            if not anyg.empty:
                wavg = float(anyg.tail(settings.history_window).mean())
                notes.append(f"No {sem} history — used all-term average")
            else:
                wavg = float(settings.default_elective_demand)
                notes.append("No history — default elective demand")
            trend, centroid_year, terms_used = 0.0, year, 0
        else:
            w = np.arange(1, len(g) + 1, dtype=float)
            wavg = float(np.average(g["students"], weights=w))
            centroid_year = float(np.average(g["year"], weights=w))
            terms_used = len(g)
            trend = 0.0
            if settings.apply_trend and len(g) >= 3 and g["year"].nunique() >= 3:
                slope = np.polyfit(g["year"].astype(float), g["students"].astype(float), 1)[0]
                mean = g["students"].mean()
                trend = float(np.clip(slope / mean if mean else 0.0,
                                      -settings.max_annual_trend, settings.max_annual_trend))
        years_ahead = max(0.0, year - centroid_year)
        projected = int(round(wavg * (1 + trend) ** years_ahead * settings.growth_multiplier))

        core = code in MANDATORY_CORE
        unseated = 0
        if not core and not virt and projected < settings.min_elective_demand:
            notes.append(f"Below {settings.min_elective_demand}-student elective threshold")
            caps = []
        else:
            caps, unseated = _section_caps_for(code, virt, projected, hist_cap.get((code, virt), np.nan), settings)
            if unseated:
                std = min(caps) if caps else settings.small_section_cap
                notes.append(f"{unseated} student{'s' if unseated != 1 else ''} over capacity — another section would be under half full "
                             f"(needs {math.ceil(HALF_FULL * std)}+ students)")

        act = actual[(actual["course"] == code) & (actual["virtual"] == virt)]
        rows.append({
            "_code": code,
            "_virtual": virt,
            "_caps": caps,
            "_n_large": _large_lecture_count(code, virt, projected, settings) if caps else 0,
            "_unseated": unseated,
            "Course": f"ECON {code}",
            "Title": catalog.get(code, ""),
            "Category": course_category(code),
            "Level": course_level(code),
            "Modality": "Online (Async)" if virt else "In-Person",
            "History Terms Used": terms_used,
            "Hist. Weighted Avg": int(round(wavg)),
            "Annual Trend": trend,
            "Projected Enrollment": projected,
            "Planned Sections": len(caps),
            "Section Caps": ", ".join(str(c) for c in caps) if caps else "—",
            "Seats Offered": int(sum(caps)),
            "Seat Fill %": (projected / sum(caps)) if caps else 0.0,
            "Actual Enrollment (if known)": int(act["ug_enr"].sum()) if not act.empty else None,
            "Actual Sections (if known)": int(len(act)) if not act.empty else None,
            "Notes": "; ".join(notes),
        })

    demand = pd.DataFrame(rows)

    # --- Recitations: only students in large lecture sections need them ----------
    # Small (e.g. 45-seat) and remote sections of the same course have no recitation.
    rec_rows = []
    for rec_code, lecture in RECITATION_FOR.items():
        lec = demand[(demand["_code"] == lecture) & (~demand["_virtual"])]
        n_large = int(lec["_n_large"].sum()) if not lec.empty else 0
        total = int(sum(_large_lecture_students(r) for _, r in lec.iterrows()))
        n = math.ceil(total / settings.recitation_cap) if total else 0
        act = enr[(enr["course"] == rec_code) & (enr["ordinal"] == target_ord)]
        rec_rows.append({
            "_code": rec_code, "_virtual": False, "_caps": [settings.recitation_cap] * n, "_n_large": 0, "_unseated": 0,
            "Course": f"ECON {rec_code}", "Title": catalog.get(rec_code, f"Recitation for ECON {lecture}"),
            "Category": "Recitation", "Level": 1000, "Modality": "In-Person",
            "History Terms Used": 0, "Hist. Weighted Avg": None, "Annual Trend": 0.0,
            "Projected Enrollment": total, "Planned Sections": n,
            "Section Caps": f"{n} × {settings.recitation_cap}" if n else "—",
            "Seats Offered": n * settings.recitation_cap,
            "Seat Fill %": (total / (n * settings.recitation_cap)) if n else 0.0,
            "Actual Enrollment (if known)": int(act["ug_enr"].sum()) if not act.empty else None,
            "Actual Sections (if known)": int(len(act)) if not act.empty else None,
            "Notes": (f"ceil({total} students in {n_large} large lecture{'s' if n_large != 1 else ''} "
                      f"/ {settings.recitation_cap}) — 1×/week, 65 min" if n_large else
                      f"No large lecture sections planned — smaller sections of ECON {lecture} don't need recitations"),
        })
    demand = pd.concat([demand, pd.DataFrame(rec_rows)], ignore_index=True)
    demand["_core"] = demand["_code"].apply(is_core)
    return demand.sort_values(["_core", "_code", "_virtual"], ascending=[False, True, True]).reset_index(drop=True)


def _large_lecture_students(row) -> int:
    """Students seated in a demand row's large-lecture sections (same split as plan_sections)."""
    caps, n = row["_caps"], int(row.get("_n_large", 0) or 0)
    if not caps or not n:
        return 0
    total_cap = sum(caps)
    return int(sum(min(cap, round(row["Projected Enrollment"] * cap / total_cap)) for cap in caps[:n]))


def plan_sections(demand: pd.DataFrame, settings: Settings) -> list[dict]:
    """
    Expand demand rows into individual sections. Projected enrollment is spread
    across sections in proportion to capacity. Recitations are distributed over
    the in-person lecture sections of their parent course (largest remainder),
    and each recitation is linked to one lecture section so the scheduler can
    keep them from overlapping. Only large lecture sections get recitations.
    """
    sections: list[dict] = []
    counters: dict[int, int] = {}

    def next_no(code):
        counters[code] = counters.get(code, 0) + 1
        return counters[code]

    for _, row in demand[~demand["_code"].isin(RECITATION_FOR)].iterrows():
        caps = row["_caps"]
        if not caps:
            continue
        total_cap = sum(caps)
        n_large = int(row.get("_n_large", 0) or 0)
        for i, cap in enumerate(caps):
            code = int(row["_code"])
            no = next_no(code)
            sections.append({
                "id": f"ECON {code}-{no:02d}",
                "code": code, "section": f"{no:02d}", "title": row["Title"],
                "category": row["Category"], "level": int(row["Level"]),
                "virtual": bool(row["_virtual"]), "cap": int(cap),
                "projected": int(min(cap, round(row["Projected Enrollment"] * cap / total_cap))),
                "kind": "Lecture", "parent": None, "large": cap >= 100 or i < n_large,
                "large_lecture": i < n_large,
                "instructor": None, "basis": "", "slot": None,
            })

    for rec_code, lecture in RECITATION_FOR.items():
        row = demand[demand["_code"] == rec_code]
        if row.empty or not row.iloc[0]["_caps"]:
            continue
        n_rec = len(row.iloc[0]["_caps"])
        lectures = [s for s in sections if s["code"] == lecture and s.get("large_lecture") and not s["virtual"]]
        if not lectures:
            continue
        total = sum(s["projected"] for s in lectures) or 1
        raw = [n_rec * s["projected"] / total for s in lectures]
        alloc = [int(math.floor(x)) for x in raw]
        for i in sorted(range(len(raw)), key=lambda i: raw[i] - alloc[i], reverse=True)[: n_rec - sum(alloc)]:
            alloc[i] += 1
        for lec, k in zip(lectures, alloc):
            for _ in range(k):
                no = next_no(rec_code)
                sections.append({
                    "id": f"ECON {rec_code}-{no:02d}",
                    "code": rec_code, "section": f"{no:02d}", "title": row.iloc[0]["Title"],
                    "category": "Recitation", "level": 1000, "virtual": False,
                    "cap": settings.recitation_cap,
                    "projected": int(min(settings.recitation_cap, math.ceil(lec["projected"] / k))),
                    "kind": "Recitation", "parent": lec["id"], "large": False, "large_lecture": False,
                    "instructor": None, "basis": "", "slot": None,
                })
    return sections


# ==============================================================================
# PREFERENCES, ROSTER & FACULTY PROFILES
# ==============================================================================
def load_preferences(source=PREFERENCES_FILE) -> tuple[dict, list[str]]:
    """
    Parse teacher_preferences.csv as written by TEACHER_PREFERENCES.py.
    Keeps each faculty member's most recent submission. Tolerates both the
    current column set ('Course Overload' + 'Overload Semester') and the older
    'Course Overload Interest' column.
    """
    warnings: list[str] = []
    try:
        df = pd.read_csv(source) if isinstance(source, str) else source.copy()
    except FileNotFoundError:
        return {}, ["teacher_preferences.csv not found — no form submissions loaded."]
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
        return {}, [f"Could not read teacher_preferences.csv: {e}"]
    if df.empty or "Full Name" not in df.columns:
        return {}, []

    if "Timestamp" in df.columns:
        df["_ts"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        df = df.sort_values("_ts", na_position="first")
    prefs: dict[str, dict] = {}
    for _, row in df.iterrows():
        name = str(row.get("Full Name", "")).strip()
        if not name or name.lower() in ("nan", "select your name..."):
            continue
        ranks, seen = [], set()
        for i in range(1, 7):
            for code in extract_codes(row.get(f"Rank {i} Course")):
                if code >= 5000:
                    warnings.append(f"{name}: ranked graduate course ECON {code} — ignored (UG only).")
                elif code not in seen:
                    ranks.append(code)
                    seen.add(code)
        principles = [c for c in extract_codes(row.get("Principles Preferences")) if c in PRINCIPLES_LECTURES]
        overload_raw = row.get("Course Overload", row.get("Course Overload Interest", "No"))
        overload = str(overload_raw).strip().lower() in ("yes", "true", "1", "y")
        ov_sem = str(row.get("Overload Semester", "None")).strip().title() if overload else "None"
        if overload and ov_sem in ("None", "Nan", ""):
            ov_sem = "Both"
        circ = str(row.get("Unique Circumstances", "")).strip()
        prefs[name] = {
            "ranks": ranks,
            "principles": principles,
            "Fall": safe_int(row.get("Fall Desired Courses")),
            "Spring": safe_int(row.get("Spring Desired Courses")),
            "overload": overload,
            "overload_semester": ov_sem,
            "circumstances": "" if circ.lower() in ("none", "nan") else circ,
        }
    return prefs, warnings


def load_overloads(path=OVERLOADS_FILE) -> dict:
    return _load_json(path, {})


def load_faculty_list(enr: pd.DataFrame) -> list[str]:
    names = _load_json(FACULTY_FILE, None)
    if not names:
        names = sorted(enr.loc[~enr["is_grad"], "instructor"].unique())
    return [n for n in names if n and n != "Select your name..."]


def teaching_history(enr: pd.DataFrame, target_ord: int) -> pd.DataFrame:
    """Recency-weighted count of sections each instructor taught per course (UG, prior terms)."""
    h = enr[(~enr["is_grad"]) & (enr["ordinal"] < target_ord) & (enr["instructor"] != "")].copy()
    h["w"] = 1.0 / (1 + (target_ord - h["ordinal"]) / 4)   # ~halves every 2 years
    return h.groupby(["instructor", "course"]).agg(count=("course", "size"), weight=("w", "sum")).reset_index()


def infer_roster(enr: pd.DataFrame, names: list[str], saved: dict | None = None) -> pd.DataFrame:
    """
    Suggest a faculty group for each name from teaching history. This is only a
    starting point — the department should confirm it in the Faculty Roster tab
    (saved to faculty_roster.json), which always takes precedence.
    """
    if saved is None:
        saved = _load_json(ROSTER_FILE, {})
    rows = []
    for name in names:
        h = enr[enr["instructor"] == name]
        ug = h[~h["is_grad"]]
        rec_share = ug["course"].isin(RECITATION_FOR).mean() if len(ug) else 0.0
        lectures = ug[~ug["course"].isin(RECITATION_FOR)]
        acad_years = h.apply(lambda r: r["year"] if r["sem"] == "Fall" else r["year"] - 1, axis=1)
        n_years = max(1, acad_years.nunique()) if len(h) else 1
        per_year = len(lectures) / n_years
        grad = h[h["is_grad"] & (h["course"] < 9000)]
        grad_per_year = len(grad) / n_years
        total_per_year = per_year + grad_per_year
        if len(ug) and rec_share >= 0.6:
            ftype = "Recitation Leader"
        elif total_per_year >= 4.5:
            ftype = "Full-Time Teaching"       # teaching-track load (6/yr)
        elif len(grad):
            ftype = TENURED                    # research faculty also teaching grad
        elif per_year <= 2 and h["ordinal"].nunique() <= 4:
            ftype = "Adjunct"
        else:
            ftype = TENURED
        # Graduate teaching (out of scope here) still consumes contracted load
        reduction = int(round(grad_per_year)) if ftype not in ("Recitation Leader", "Adjunct") else 0
        source = "Inferred from history"
        if name in saved:
            ftype = normalize_faculty_type(saved[name].get("type", ftype))
            reduction = safe_int(saved[name].get("reduction"), reduction)
            source = "Confirmed"
        rows.append({"Faculty": name, "Type": ftype, "Annual Reduction": reduction,
                     "UG Lectures / Yr (hist.)": round(per_year, 1),
                     "Grad Sections / Yr (hist.)": round(grad_per_year, 1), "Source": source})
    return pd.DataFrame(rows)


def save_roster(roster: pd.DataFrame, path=ROSTER_FILE):
    data = {r["Faculty"]: {"type": r["Type"], "reduction": safe_int(r["Annual Reduction"], 0)}
            for _, r in roster.iterrows()}
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


@dataclass
class FacultyProfile:
    name: str
    ftype: str
    reduction: int
    submitted: bool
    term_target: int                  # max sections to assign this term
    other_term_planned: int           # planned load for the other semester
    target_source: str
    overload_approved: bool           # faculty_overloads.json, this semester
    overload_requested: bool          # preference form, this semester
    overload_approved_annual: int     # number of approved overload semesters/yr
    scores: dict = field(default_factory=dict)   # course -> (score, basis)
    circumstances: str = ""
    assigned: list = field(default_factory=list)  # section ids
    slots: list = field(default_factory=list)     # slot codes

    @property
    def remaining(self) -> int:
        return self.term_target - len(self.assigned)


def _opt_int(v):
    """int, or None for missing / NaN values."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return int(v)


def _semester_matches(sem_value: str, sem: str) -> bool:
    return str(sem_value).title() in (sem, "Both")


def build_faculty_profiles(enr, roster, prefs, overloads, settings: Settings) -> dict[str, FacultyProfile]:
    sem, year = settings.target
    other = "Spring" if sem == "Fall" else "Fall"
    target_ord = term_ordinal(sem, year)
    hist = teaching_history(enr, target_ord)
    ug_prior = enr[(~enr["is_grad"]) & (enr["ordinal"] < target_ord)]
    recent_ords = set(sorted(ug_prior["ordinal"].unique())[-4:])

    def hist_avg(name, which, recitations=False):
        terms = sorted(ug_prior.loc[ug_prior["sem"] == which, "ordinal"].unique())[-2:]
        if not terms:
            return 0
        h = ug_prior[(ug_prior["instructor"] == name) & ug_prior["ordinal"].isin(terms)]
        h = h[h["course"].isin(RECITATION_FOR)] if recitations else h[~h["course"].isin(RECITATION_FOR)]
        return int(math.floor(len(h) / len(terms) + 0.5))

    profiles = {}
    roster_map = roster.set_index("Faculty").to_dict("index")
    names = list(dict.fromkeys(list(roster_map) + list(prefs)))
    for name in names:
        r = roster_map.get(name, {"Type": "Adjunct", "Annual Reduction": 0})
        ftype = normalize_faculty_type(r["Type"])
        ftype = ftype if ftype in FACULTY_TYPES else "Adjunct"
        contract = FACULTY_TYPES[ftype]
        p = prefs.get(name)
        ov = overloads.get(name, {})
        approved = bool(ov.get("overloading")) and _semester_matches(ov.get("semester", "None"), sem)
        approved_annual = 0
        if ov.get("overloading"):
            approved_annual = 2 if str(ov.get("semester")).title() == "Both" else 1
        requested = bool(p and p["overload"] and _semester_matches(p["overload_semester"], sem))
        active = bool(set(enr.loc[enr["instructor"] == name, "ordinal"]) & recent_ords)
        is_leader = ftype == "Recitation Leader"

        # --- term target & other-semester plan ---------------------------------
        if p and p.get(sem) is not None:
            target, other_plan, source = p[sem], (p.get(other) or 0), "Preference form"
        elif settings.history_fallback and active:
            if is_leader:
                target = max(hist_avg(name, sem, recitations=True), settings.recitation_leader_load)
                other_plan = hist_avg(name, other, recitations=True)
            else:
                target, other_plan = hist_avg(name, sem), hist_avg(name, other)
            source = "Teaching history"
        else:
            target, other_plan, source = 0, 0, "No submission"
        if contract and not p and target + other_plan > 0:
            # History-based targets never exceed the contract (+ approved overloads);
            # scale both semesters down proportionally when history runs over.
            allowed = max(0, contract["max"] - r.get("Annual Reduction", 0)) + approved_annual
            if target + other_plan > allowed:
                scale = allowed / (target + other_plan)
                target = int(math.floor(target * scale + 0.5))
                other_plan = max(0, allowed - target)

        # Scheduler-set semester courseloads (Administration) are authoritative
        set_this, set_other = _opt_int(r.get(f"{sem} Courseload")), _opt_int(r.get(f"{other} Courseload"))
        if set_this is not None:
            target, source = set_this, "Scheduler courseload"
        if set_other is not None:
            other_plan = set_other

        # --- willingness scores per course -----------------------------------
        scores: dict[int, tuple[float, str]] = {}
        h = hist[hist["instructor"] == name].set_index("course")
        for code, hr in h.iterrows():
            bonus = min(2.0, 0.5 * hr["weight"])
            if p:
                # Submitters: history only lets them cover core courses (fallback)
                if is_core(code):
                    scores[code] = (1.0 + bonus, "Teaching history (not ranked)")
            elif settings.history_fallback and active:
                scores[code] = (3.0 + min(3.0, hr["weight"]), f"Teaching history ({int(hr['count'])}× taught)")
        if p:
            for code in p["principles"]:
                b = min(2.0, 0.5 * h["weight"].get(code, 0.0)) if not h.empty else 0.0
                scores[code] = (7.0 + b, "Principles preference")
            for i, code in enumerate(p["ranks"], start=1):
                b = min(2.0, 0.5 * h["weight"].get(code, 0.0)) if not h.empty else 0.0
                scores[code] = (max(scores.get(code, (0, ""))[0], 10.0 - i + b), f"Rank {i} preference")
        if is_leader:
            scores = {c: v for c, v in scores.items() if c in RECITATION_FOR}
        else:
            scores = {c: v for c, v in scores.items() if c not in RECITATION_FOR}

        profiles[name] = FacultyProfile(
            name=name, ftype=ftype, reduction=int(r.get("Annual Reduction", 0) or 0),
            submitted=bool(p), term_target=int(max(0, target)), other_term_planned=int(other_plan),
            target_source=source, overload_approved=approved, overload_requested=requested,
            overload_approved_annual=approved_annual, scores=scores,
            circumstances=(p or {}).get("circumstances", ""),
        )
    return profiles


# ==============================================================================
# INSTRUCTOR MATCHING
# ==============================================================================
def _min_cost_flow(n_nodes: int, edges: list[tuple[int, int, int, float]], src: int, sink: int, flow: int):
    """
    Successive-shortest-path min-cost flow (Bellman-Ford/SPFA). Small and
    dependency-free; graphs here are ~200 nodes / a few thousand edges.
    `edges` = (u, v, capacity, cost). Returns the flow on each input edge.
    """
    graph = [[] for _ in range(n_nodes)]
    # edge record: [to, cap, cost, rev_index, original_edge_index or -1]
    for i, (u, v, cap, cost) in enumerate(edges):
        graph[u].append([v, cap, cost, len(graph[v]), i])
        graph[v].append([u, 0, -cost, len(graph[u]) - 1, -1])
    sent = 0
    while sent < flow:
        dist = [float("inf")] * n_nodes
        in_q = [False] * n_nodes
        prev = [None] * n_nodes
        dist[src] = 0.0
        queue = [src]
        while queue:
            u = queue.pop(0)
            in_q[u] = False
            for idx, (v, cap, cost, _, _) in enumerate(graph[u]):
                if cap > 0 and dist[u] + cost < dist[v] - 1e-9:
                    dist[v] = dist[u] + cost
                    prev[v] = (u, idx)
                    if not in_q[v]:
                        queue.append(v)
                        in_q[v] = True
        if dist[sink] == float("inf"):
            break
        v = sink
        while v != src:  # every path carries one unit (section capacities are 1)
            u, idx = prev[v]
            graph[u][idx][1] -= 1
            rev = graph[u][idx][3]
            graph[v][rev][1] += 1
            v = u
        sent += 1
    result = [0] * len(edges)
    for u in range(n_nodes):
        for v, cap, cost, rev, orig in graph[u]:
            if orig >= 0:
                result[orig] = edges[orig][2] - cap
    return result


# Cost of leaving a section without an instructor (relative to preference scores ~1-11)
UNSTAFFED_COST = {"core": 100.0, "recitation": 50.0, "elective": 0.0}
FORCED_COST = 20.0
LOAD_SPREAD_COST = 0.4   # marginal cost of each extra section given to the same person


def assign_instructors(sections: list[dict], profiles: dict[str, FacultyProfile],
                       settings: Settings) -> tuple[list[dict], list[dict]]:
    """
    Globally optimal preference matching as a min-cost flow:

        source -> section (1) -> faculty (willing only) -> sink (term target units)
                         \-> "unstaffed" bypass ----------------------^

    * Assigning a section costs -(preference score), so higher ranks win.
    * Leaving a mandatory core section unstaffed costs 100, a recitation 50 and
      an elective 0 — core courses are therefore staffed first whenever anyone
      willing has capacity, and an elective is offered only if a willing
      instructor is left over (electives are preference-driven).
    * Each additional section given to the same person costs a little more,
      spreading load instead of piling onto the highest scorer.
    * Optional force-fill: any non-recitation faculty with spare capacity can
      cover an otherwise-unstaffed core section at a high (but < 100) cost.
    Returns (scheduled_sections, dropped_elective_sections).
    """
    names = [n for n, p in profiles.items() if p.term_target > 0]
    n_sec, n_fac = len(sections), len(names)
    SRC, SINK = 0, n_sec + n_fac + 2
    DUMMY = n_sec + n_fac + 1
    fac_node = {n: n_sec + 1 + i for i, n in enumerate(names)}

    edges, meta = [], []   # meta: (section_index, faculty_name or None, forced)
    for i, sec in enumerate(sections):
        node = 1 + i
        edges.append((SRC, node, 1, 0.0)); meta.append(None)
        code = sec["code"]
        demand_bonus = min(1.0, sec["projected"] / 100.0)
        kind = "recitation" if sec["kind"] == "Recitation" else ("core" if code in MANDATORY_CORE else "elective")
        for name in names:
            p = profiles[name]
            if code in p.scores:
                edges.append((node, fac_node[name], 1, -(p.scores[code][0] + demand_bonus)))
                meta.append((i, name, False))
            elif (settings.force_fill_core and kind == "core" and p.ftype != "Recitation Leader"):
                edges.append((node, fac_node[name], 1, FORCED_COST))
                meta.append((i, name, True))
        edges.append((node, DUMMY, 1, UNSTAFFED_COST[kind])); meta.append((i, None, False))
    for name in names:
        for k in range(profiles[name].term_target):
            edges.append((fac_node[name], SINK, 1, LOAD_SPREAD_COST * k)); meta.append(None)
    edges.append((DUMMY, SINK, n_sec, 0.0)); meta.append(None)

    flows = _min_cost_flow(SINK + 1, edges, SRC, SINK, n_sec)

    dropped = []
    for f, m in zip(flows, meta):
        if not f or m is None:
            continue
        i, name, forced = m
        sec = sections[i]
        if name is None:
            if sec["kind"] == "Recitation":
                sec["instructor"], sec["basis"] = RECITATION_TBA, "No recitation leader available"
            elif sec["code"] in MANDATORY_CORE:
                sec["instructor"], sec["basis"] = UNSTAFFED, "No willing instructor"
            else:
                dropped.append(sec)
            continue
        sec["instructor"] = name
        sec["basis"] = "Forced assignment — review" if forced else profiles[name].scores[sec["code"]][1]
        profiles[name].assigned.append(sec["id"])

    dropped_ids = {s["id"] for s in dropped}
    return [s for s in sections if s["id"] not in dropped_ids], dropped


# ==============================================================================
# TIME-SLOT ASSIGNMENT
# ==============================================================================
def slot_popularity(enr: pd.DataFrame) -> dict[str, float]:
    """Historical average fill rate per class sequence, scaled to 0..1 (student time preference)."""
    h = enr[(~enr["is_grad"]) & enr["seq"].notna() & (enr["max_enr"] > 0)]
    if h.empty:
        return {}
    fill = (h["ug_enr"] / h["max_enr"]).clip(upper=1.2).groupby(h["seq"]).mean()
    lo, hi = fill.min(), fill.max()
    return {k: (float(v - lo) / (hi - lo) if hi > lo else 0.5) for k, v in fill.items()}


def assign_time_slots(sections: list[dict], profiles: dict[str, FacultyProfile],
                      popularity: dict[str, float]) -> list[dict]:
    """
    Assign each in-person lecture a class sequence (1-5, A-H) and each
    recitation a 65-minute lab-window slot (L-W).
      Hard: an instructor never teaches two overlapping meetings.
      Hard: a recitation never overlaps its linked lecture section.
      Soft: spread sections of the same course, avoid stacking same-stage core
            courses, balance slot usage, favour historically popular times,
            and keep recitations clear of *all* lectures of their parent course.
    """
    by_id = {s["id"]: s for s in sections}
    usage = {k: 0 for k in ALL_SLOTS}
    placed: list[dict] = []

    def instructor_busy(name, code):
        prof = profiles.get(name)
        return bool(prof and any(slots_overlap(code, other) for other in prof.slots))

    def place(sec, code):
        sec["slot"] = code
        usage[code] += 1
        placed.append(sec)
        if sec["instructor"] in profiles:
            profiles[sec["instructor"]].slots.append(code)

    for sec in sections:
        if sec["virtual"]:
            sec["slot"] = ASYNC_SLOT

    lectures = [s for s in sections if s["kind"] == "Lecture" and not s["virtual"]]
    load = {n: len(p.assigned) for n, p in profiles.items()}
    lectures.sort(key=lambda s: (not is_core(s["code"]), not s["large"], -load.get(s["instructor"], 0)))
    for sec in lectures:
        best, best_cost = None, float("inf")
        for code in CLASS_SEQUENCES:
            if instructor_busy(sec["instructor"], code):
                continue
            cost = usage[code] * 1.0 - 2.0 * popularity.get(code, 0.5)
            for o in placed:
                if not slots_overlap(code, o["slot"]):
                    continue
                if o["code"] == sec["code"]:
                    cost += 10
                elif CORE_STAGE.get(o["code"]) and CORE_STAGE.get(o["code"]) == CORE_STAGE.get(sec["code"]):
                    cost += 4
            if cost < best_cost:
                best, best_cost = code, cost
        if best:
            place(sec, best)
        else:
            sec["slot"] = UNSCHEDULED

    recs = [s for s in sections if s["kind"] == "Recitation"]
    for sec in recs:
        parent = by_id.get(sec["parent"])
        parent_slot = parent["slot"] if parent else None
        siblings = [s for s in placed if parent and s["code"] == parent["code"] and s["kind"] == "Lecture"]
        best, best_cost = None, float("inf")
        for code in RECITATION_SLOTS:
            if parent_slot and slots_overlap(code, parent_slot):
                continue
            if instructor_busy(sec["instructor"], code):
                continue
            cost = usage[code] * 1.0
            cost += 8 * sum(slots_overlap(code, s["slot"]) for s in siblings)
            cost += 5 * sum(1 for o in placed if o["code"] == sec["code"] and slots_overlap(code, o["slot"]))
            if cost < best_cost:
                best, best_cost = code, cost
        if best:
            place(sec, best)
        else:
            sec["slot"] = UNSCHEDULED
    return sections


# ==============================================================================
# 9. MASTER TABLE, CONFLICTS & WORKLOAD
# ==============================================================================
MASTER_COLUMNS = [
    "Section ID", "Course", "Section", "Title", "Category", "Level", "Component", "Modality",
    "Section Cap", "Projected Enrollment", "Instructor", "Faculty Type", "Match Basis",
    "Sequence", "Sequence Type", "Days", "Meeting Time", "Linked Lecture", "Prerequisites",
]


def sections_to_master(sections: list[dict], profiles: dict[str, FacultyProfile]) -> pd.DataFrame:
    rows = []
    for s in sections:
        rows.append({
            "Section ID": s["id"], "Course": f"ECON {s['code']}", "Section": s["section"],
            "Title": s["title"], "Category": s["category"], "Level": s["level"],
            "Component": s["kind"], "Modality": "Online (Async)" if s["virtual"] else "In-Person",
            "Section Cap": s["cap"], "Projected Enrollment": s["projected"],
            "Instructor": s["instructor"] or UNSTAFFED, "Match Basis": s["basis"],
            "Sequence": s["slot"] or UNSCHEDULED, "Linked Lecture": s["parent"] or "",
            "Prerequisites": format_prereqs(get_prerequisites(s["code"])),
        })
    return finalize_master(pd.DataFrame(rows), profiles)


def finalize_master(master: pd.DataFrame, profiles: dict[str, FacultyProfile]) -> pd.DataFrame:
    """Recompute derived columns (days, times, faculty type). Safe to call after manual edits."""
    m = master.copy()
    if m.empty:
        return pd.DataFrame(columns=MASTER_COLUMNS)
    m["Instructor"] = m["Instructor"].fillna(UNSTAFFED).replace("", UNSTAFFED)
    m["Sequence"] = m["Sequence"].fillna(UNSCHEDULED).replace("", UNSCHEDULED)
    desc = m["Sequence"].apply(describe_slot)
    m["Days"] = desc.str[0]
    m["Meeting Time"] = desc.str[1]
    m["Sequence Type"] = m["Sequence"].apply(slot_type)
    m["Faculty Type"] = m["Instructor"].apply(lambda n: profiles[n].ftype if n in profiles else "—")
    m["_course"] = m["Course"].str.extract(r"(\d{4})")[0].astype(int)
    m["_core"] = m["_course"].apply(is_core)
    m = m.sort_values(["_core", "_course", "Component", "Section"],
                      ascending=[False, True, True, True]).drop(columns=["_course", "_core"])
    return m[MASTER_COLUMNS].reset_index(drop=True)


def _conflict(sev, cat, course, faculty, detail, action):
    return {"Severity": sev, "Category": cat, "Course / Section": course,
            "Faculty": faculty, "Details": detail, "Suggested Action": action}


def workload_summary(master: pd.DataFrame, profiles: dict[str, FacultyProfile], settings: Settings) -> pd.DataFrame:
    """Per-faculty load this term + planned other term vs. contract and overloads."""
    sem, _ = settings.target
    counts = master[master["Instructor"].isin(profiles)].groupby("Instructor").size()
    rows = []
    for name, p in profiles.items():
        assigned = int(counts.get(name, 0))
        if assigned == 0 and p.term_target == 0 and not p.submitted:
            continue  # inactive this term with no form — omit from the report
        contract = FACULTY_TYPES.get(p.ftype)
        annual = assigned + p.other_term_planned
        if contract is None:
            status = "✅ Recitation leader (no course contract)"
            rng = "—"
            lo = hi = None
        else:
            lo = max(0, contract["min"] - p.reduction)
            base_hi = max(0, contract["max"] - p.reduction)
            hi = base_hi + p.overload_approved_annual
            rng = f"{lo}–{hi}" + (f" (incl. {p.overload_approved_annual} overload)" if p.overload_approved_annual else "")
            if annual > hi:
                status = "❌ Over contract"
            elif annual < lo:
                status = "⚠️ Under contract"
            elif annual > base_hi:
                status = "💲 Overload in use"
            elif p.ftype == TENURED and annual < contract["standard"] - p.reduction:
                status = "ℹ️ Below standard (tenured)"
            else:
                status = "✅ Within contract"
        rows.append({
            "Faculty": name, "Type": p.ftype, "Target Source": p.target_source,
            f"{sem} Target": p.term_target, f"Assigned ({sem})": assigned,
            "Other Semester Planned": p.other_term_planned, "Projected Annual": annual,
            "Allowed Annual": rng, "Annual Reduction": p.reduction,
            "Overload Approved (JSON)": "Yes" if p.overload_approved else "No",
            "Overload Requested (Form)": "Yes" if p.overload_requested else "No",
            "Status": status,
        })
    return pd.DataFrame(rows).sort_values(["Status", "Faculty"]).reset_index(drop=True) if rows else pd.DataFrame()


def unseated_demand(demand: pd.DataFrame) -> list[dict]:
    """Courses whose projected students exceed planned seats because of the half-full rule."""
    out = []
    if demand is None or demand.empty or "_unseated" not in demand:
        return out
    for _, r in demand[demand["_unseated"].fillna(0) > 0].iterrows():
        caps = r["_caps"] or []
        out.append({"code": int(r["_code"]), "virtual": bool(r["_virtual"]), "unseated": int(r["_unseated"]),
                    "projected": int(r["Projected Enrollment"]),
                    "sections": len(caps), "seats": int(sum(caps)),
                    "half": math.ceil(HALF_FULL * (min(caps) if caps else 0))})
    return out


def detect_conflicts(master: pd.DataFrame, profiles: dict[str, FacultyProfile], settings: Settings,
                     prereq_df: pd.DataFrame | None = None, dropped: list[dict] | None = None,
                     pref_warnings: list[str] | None = None, unseated: list[dict] | None = None,
                     manual_codes: set | None = None) -> pd.DataFrame:
    """
    Build the Unresolved Conflicts Report from the (possibly hand-edited) master table.
    `manual_codes`: courses a scheduler added sections for by hand; their "Elective not
    offered" and "Demand over capacity" items are treated as resolved.
    """
    manual_codes = manual_codes or set()
    sem, _ = settings.target
    out = []
    m = master.copy()
    m["_code"] = m["Course"].str.extract(r"(\d{4})")[0].astype(int)

    # --- Coverage ---------------------------------------------------------------
    offered = set(m["_code"])
    for code in MANDATORY_CORE:
        if code not in offered:
            out.append(_conflict("Critical", "Missing core course", f"ECON {code}", "—",
                                 "Mandatory core course has no sections planned.",
                                 "Add a section manually or check enrollment history."))
    for _, r in m.iterrows():
        if r["Instructor"] == UNSTAFFED:
            core = r["_code"] in MANDATORY_CORE
            out.append(_conflict("Critical" if core else "Warning", "Unstaffed section", r["Section ID"], "—",
                                 f"{r['Title']} has no instructor ({r['Match Basis'] or 'unassigned'}).",
                                 "Recruit an adjunct, approve an overload, or reassign from an elective."))
        elif r["Instructor"] == RECITATION_TBA:
            out.append(_conflict("Warning", "Unstaffed recitation", r["Section ID"], "—",
                                 "No recitation leader available.", "Assign a TA / recitation leader."))
        elif r["Instructor"] not in profiles:
            out.append(_conflict("Warning", "Unknown instructor", r["Section ID"], r["Instructor"],
                                 "Instructor is not on the faculty roster.", "Check spelling or add to roster."))
        if "Forced" in str(r["Match Basis"]):
            out.append(_conflict("Warning", "Assignment outside preferences", r["Section ID"], r["Instructor"],
                                 "Core section force-assigned to a faculty member who did not request it.",
                                 "Confirm with the faculty member."))

    # --- Capacity ---------------------------------------------------------------
    for _, r in m.iterrows():
        if r["Modality"].startswith("Online") and r["Section Cap"] > VIRTUAL_CAP_LIMIT:
            out.append(_conflict("Critical", "Remote cap exceeded", r["Section ID"], r["Instructor"],
                                 f"Remote section cap {r['Section Cap']} > {VIRTUAL_CAP_LIMIT}.",
                                 f"Reduce cap to {VIRTUAL_CAP_LIMIT} or add a section."))
        if r["Projected Enrollment"] > r["Section Cap"]:
            out.append(_conflict("Warning", "Over capacity", r["Section ID"], r["Instructor"],
                                 f"Projected {r['Projected Enrollment']} > cap {r['Section Cap']}.",
                                 "Raise the cap or add a section."))

    # --- Schedule ---------------------------------------------------------------
    inperson = m[m["Modality"] == "In-Person"]
    for _, r in inperson[inperson["Sequence"].isin([UNSCHEDULED]) | ~inperson["Sequence"].isin(ALL_SLOTS)].iterrows():
        out.append(_conflict("Critical", "Unscheduled section", r["Section ID"], r["Instructor"],
                             "No conflict-free time slot was available.", "Pick a sequence manually."))
    sched = inperson[inperson["Sequence"].isin(ALL_SLOTS)]
    for name, g in sched.groupby("Instructor"):
        if name in (UNSTAFFED, RECITATION_TBA):
            continue
        recs = g.to_dict("records")
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                if slots_overlap(recs[i]["Sequence"], recs[j]["Sequence"]):
                    out.append(_conflict("Critical", "Instructor time overlap",
                                         f"{recs[i]['Section ID']} ↔ {recs[j]['Section ID']}", name,
                                         f"Sequences {recs[i]['Sequence']} and {recs[j]['Sequence']} overlap.",
                                         "Move one section to a different sequence."))
    by_id = m.set_index("Section ID")
    for _, r in sched[sched["Component"] == "Recitation"].iterrows():
        parent = r["Linked Lecture"]
        if parent in by_id.index and slots_overlap(r["Sequence"], by_id.loc[parent, "Sequence"]):
            out.append(_conflict("Critical", "Recitation overlaps lecture", f"{r['Section ID']} ↔ {parent}",
                                 r["Instructor"], "Recitation meets at the same time as its linked lecture.",
                                 "Move the recitation to another lab-window slot."))
    # Same-stage core courses whose sections ALL overlap leave students no valid combination
    core_sched = sched[sched["_code"].isin(MANDATORY_CORE) & (sched["Component"] == "Lecture")]
    codes = sorted(core_sched["_code"].unique())
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            if CORE_STAGE.get(a) != CORE_STAGE.get(b):
                continue
            sa = core_sched.loc[core_sched["_code"] == a, "Sequence"].tolist()
            sb = core_sched.loc[core_sched["_code"] == b, "Sequence"].tolist()
            if all(slots_overlap(x, y) for x in sa for y in sb):
                out.append(_conflict("Warning", "Core schedule clash", f"ECON {a} ↔ ECON {b}", "—",
                                     "Every section of these same-stage core courses overlaps.",
                                     "Move at least one section to a different sequence."))
    for code, g in core_sched.groupby("_code"):
        if len(g) > 1 and g["Sequence"].nunique() == 1:
            out.append(_conflict("Info", "Low time diversity", f"ECON {code}", "—",
                                 "All sections meet in the same sequence.", "Spread sections across sequences."))

    # --- Workload ---------------------------------------------------------------
    wl = workload_summary(master, profiles, settings)
    for _, r in wl.iterrows():
        p = profiles[r["Faculty"]]
        status = r["Status"]
        if status.startswith("❌"):
            out.append(_conflict("Warning", "Over-allocation", "—", p.name,
                                 f"{p.ftype}: projected {r['Projected Annual']}/yr exceeds allowed {r['Allowed Annual']}.",
                                 "Remove a section, or approve an overload under Administration → Faculty & Overloads."))
        elif status.startswith("⚠️"):
            out.append(_conflict("Warning", "Under-allocation", "—", p.name,
                                 f"{p.ftype}: projected {r['Projected Annual']}/yr below required {r['Allowed Annual']}.",
                                 "Assign another section, or set a lower Fall/Spring Courseload under Administration → Faculty & Overloads."))
        elif status.startswith("💲"):
            out.append(_conflict("Info", "Overload compensation", "—", p.name,
                                 "Load exceeds base contract using an approved overload.",
                                 "Process extra compensation."))
        if p.overload_approved != p.overload_requested and (p.submitted or p.overload_approved):
            out.append(_conflict("Warning", "Overload record mismatch", "—", p.name,
                                 f"faculty_overloads.json says {'Yes' if p.overload_approved else 'No'} for {sem}; "
                                 f"preference form says {'Yes' if p.overload_requested else 'No'}.",
                                 "Reconcile the admin overload record with the form."))
        if p.submitted and r[f"Assigned ({sem})"] < r[f"{sem} Target"]:
            out.append(_conflict("Info", "Below requested load", "—", p.name,
                                 f"Requested {r[f'{sem} Target']} for {sem}, assigned {r[f'Assigned ({sem})']}.",
                                 "Consider adding a preferred elective."))
        if p.circumstances:
            out.append(_conflict("Info", "Unique circumstances", "—", p.name, p.circumstances,
                                 "Review manually before finalising."))

    # --- Electives not offered, prerequisites, data warnings -------------------
    for u in unseated or []:          # already re-checked against edited seats (capacity_gaps)
        label = f"ECON {u['code']}" + (" (Remote)" if u["virtual"] else "")
        n, gone = u["unseated"], u.get("removed", 0)
        students = f"{n} projected {'student' if n == 1 else 'students'}"
        if gone and not u["sections"]:
            detail = f"Every section was deleted, so {students} {'has' if n == 1 else 'have'} no seats."
        elif gone:
            detail = (f"{students} {'exceeds' if n == 1 else 'exceed'} the {u['seats']} seats in the {u['sections']} remaining "
                      f"section{'s' if u['sections'] != 1 else ''} after {gone} section{'s were' if gone != 1 else ' was'} deleted.")
        else:
            detail = (f"{students} {'exceeds' if n == 1 else 'exceed'} the {u['seats']} seats in {u['sections']} planned "
                      f"section{'s' if u['sections'] != 1 else ''}; another section would be under half full "
                      f"(needs {u['half']}+ students).")
        action = ("Undo the deletion, add a section, or raise a section cap." if gone
                  else "Add a section manually if needed, or raise a section cap.")
        out.append(_conflict("Warning", "Demand over capacity", label, "—", detail, action))
    for sec in dropped or []:
        if sec["code"] in manual_codes:
            continue
        out.append(_conflict("Info", "Elective not offered", sec["id"], "—",
                             f"{sec['title']}: demand exists but no willing faculty with remaining capacity.",
                             "Add a section manually if a faculty member volunteers."))
    if prereq_df is not None and not prereq_df.empty:
        for _, r in prereq_df[~prereq_df["_ok"]].iterrows():
            out.append(_conflict("Warning", "Prerequisite issue", r["Course"], "—",
                                 f"{r['Level Rule']} · {r['Pathway Offered This Term']}",
                                 "Review catalog prerequisites."))
    for w in pref_warnings or []:
        out.append(_conflict("Info", "Preference data", "—", "—", w, "Check the form response."))

    order = {"Critical": 0, "Warning": 1, "Info": 2}
    df = pd.DataFrame(out, columns=["Severity", "Category", "Course / Section", "Faculty", "Details", "Suggested Action"])
    if df.empty:
        return df
    return df.sort_values(by="Severity", key=lambda s: s.map(order), kind="stable").reset_index(drop=True)


# ==============================================================================
# 10. FULL PIPELINE
# ==============================================================================
def apply_overrides(master: pd.DataFrame, overrides: dict[str, dict],
                    profiles: dict[str, FacultyProfile]) -> tuple[pd.DataFrame, list[str]]:
    """
    Apply manual edits {section_id: {"instructor": ..., "sequence": ...}} to the
    generated master table. Returns (master, ids_applied). Overrides whose
    section no longer exists (e.g. settings changed the section count) are skipped.
    """
    if not overrides or master.empty:
        return master, []
    m = master.copy()
    applied = []
    for idx, row in m.iterrows():
        ov = overrides.get(row["Section ID"])
        if not ov:
            continue
        if ov.get("instructor"):
            m.at[idx, "Instructor"] = ov["instructor"]
        if ov.get("sequence"):
            m.at[idx, "Sequence"] = ov["sequence"]
        if ov.get("cap"):
            m.at[idx, "Section Cap"] = int(ov["cap"])
        m.at[idx, "Match Basis"] = "Manual override"
        applied.append(row["Section ID"])
    return finalize_master(m, profiles), applied


def remove_sections(master: pd.DataFrame, ids: list[str]) -> tuple[pd.DataFrame, list[dict]]:
    """
    Drop sections a scheduler deleted. Recitations linked to a deleted lecture go with it
    (they only exist to serve that lecture's students). Returns (master, removed rows).
    """
    if not ids or master.empty:
        return master, []
    gone = set(ids)
    mask = master["Section ID"].isin(gone) | master["Linked Lecture"].isin(gone)
    removed = [{"section_id": r["Section ID"], "course": r["Course"], "code": int(str(r["Course"]).split()[1]),
                "title": r["Title"], "component": r["Component"], "instructor": r["Instructor"],
                "virtual": str(r["Modality"]).startswith("Online"), "section_cap": int(r["Section Cap"]),
                "linked_lecture": r["Linked Lecture"] if r["Section ID"] not in gone else ""}
               for _, r in master[mask].iterrows()]
    return master[~mask].reset_index(drop=True), removed


MANUAL_BASIS = "Manual section"


def _group_mask(master: pd.DataFrame, code: int, virtual: bool) -> pd.Series:
    """Lecture sections of one course in one modality (remote vs. in-person)."""
    return ((master["Course"] == f"ECON {code}") & (master["Component"] == "Lecture")
            & (master["Modality"].str.startswith("Online") == virtual))


def rebalance_projection(master: pd.DataFrame, demand: pd.DataFrame, groups: set) -> pd.DataFrame:
    """
    After caps change or sections are added by hand, spread each affected course's projected
    students over its actual sections in proportion to capacity (same split as plan_sections).
    """
    if not groups or master.empty:
        return master
    m = master.copy()
    proj = {(int(r["_code"]), bool(r["_virtual"])): int(r["Projected Enrollment"]) for _, r in demand.iterrows()}
    for code, virtual in groups:
        if (code, virtual) not in proj:
            continue
        mask = _group_mask(m, code, virtual)
        caps = m.loc[mask, "Section Cap"].astype(int)
        total_cap = int(caps.sum())
        if total_cap <= 0:
            continue
        m.loc[mask, "Projected Enrollment"] = [int(min(c, round(proj[(code, virtual)] * c / total_cap))) for c in caps]
    return m


def capacity_gaps(master: pd.DataFrame, unseated: list[dict], demand: pd.DataFrame | None = None,
                  removed: dict[tuple[int, bool], int] | None = None) -> list[dict]:
    """
    Re-check projected students against the seats now on the (edited) schedule; drop gaps that
    are closed. `removed` = {(code, virtual): sections deleted by hand}: those courses are
    re-checked too, since deleting a section can push demand over the remaining capacity.
    """
    removed = removed or {}
    base = {(u["code"], u["virtual"]): u for u in unseated or []}
    if demand is not None and not demand.empty:
        for (code, virtual) in removed:
            if (code, virtual) in base:
                continue
            row = demand[(demand["_code"] == code) & (demand["_virtual"] == virtual)]
            if len(row):
                base[(code, virtual)] = {"code": code, "virtual": virtual, "unseated": 0,
                                         "projected": int(row.iloc[0]["Projected Enrollment"]),
                                         "sections": 0, "seats": 0, "half": None}
    out = []
    for key, u in base.items():
        mask = _group_mask(master, u["code"], u["virtual"]) if not master.empty else None
        seats = int(master.loc[mask, "Section Cap"].sum()) if mask is not None else 0
        n = int(mask.sum()) if mask is not None else 0
        remaining = u["projected"] - seats
        if remaining > 0:
            out.append({**u, "unseated": remaining, "seats": seats, "sections": n, "removed": removed.get(key, 0)})
    return out


def suggest_time_blocks(master: pd.DataFrame, code: int, instructor: str | None, popularity: dict[str, float],
                        exclude_id: str | None = None, limit: int = 3) -> list[dict]:
    """
    Rank lecture sequences (1–5, A–H) for one extra section of `code`, against the current
    (edited) term schedule, using the solver's own soft costs:
      Hard: never overlap the instructor's existing meetings (lectures or recitations).
      Soft: avoid other sections of the same course (+10 each), core lectures (+3 each —
            students need those), same-level electives (+1 each) and crowded blocks
            (+1 per section); favour historically popular times (−2 × popularity).
    """
    m = master[master["Section ID"] != exclude_id] if exclude_id else master
    live = m[(m["Modality"] == "In-Person") & m["Sequence"].isin(ALL_SLOTS)].copy()
    live["_code"] = live["Course"].str.extract(r"(\d{4})")[0].astype(int)
    busy = live.loc[live["Instructor"] == instructor, "Sequence"].tolist() if instructor else []
    lectures = live[live["Component"] == "Lecture"]
    level = course_level(code)
    out = []
    for seq in CLASS_SEQUENCES:
        if any(slots_overlap(seq, b) for b in busy):
            continue
        hit = lectures[lectures["Sequence"].apply(lambda o: slots_overlap(seq, o))]
        same = int((hit["_code"] == code).sum())
        core = int(hit["_code"].apply(lambda c: c in MANDATORY_CORE and c != code).sum())
        peers = int(hit["_code"].apply(lambda c: c != code and not is_core(c) and course_level(c) == level).sum())
        usage = int((lectures["Sequence"] == seq).sum())
        pop = float(popularity.get(seq, 0.5))
        cost = 10 * same + 3 * core + 1 * peers + 1.0 * usage - 2.0 * pop
        reasons = [f"No overlap with {instructor}'s {len(busy)} other meeting{'s' if len(busy) != 1 else ''}" if instructor
                   else "No instructor yet — re-run after choosing one"]
        reasons.append(f"{core} core lecture section{'s' if core != 1 else ''} at this time" if core else "No core lectures at this time")
        if same:
            reasons.append(f"Overlaps {same} other section{'s' if same != 1 else ''} of ECON {code}")
        if peers:
            reasons.append(f"{peers} other {level}-level elective{'s' if peers != 1 else ''} at this time")
        out.append({"sequence": seq, "label": describe_slot(seq)[1],
                    "cost": round(cost, 2), "core_overlaps": core, "same_course_overlaps": same,
                    "level_overlaps": peers, "sections_in_block": usage, "reasons": reasons})
    out.sort(key=lambda d: (d["cost"], d["sequence"]))
    return out[:limit]


def likely_volunteers(code: int, profiles: dict[str, FacultyProfile], master: pd.DataFrame) -> list[dict]:
    """Faculty with a recorded interest in `code` (preference rank or teaching history), most willing first."""
    counts = master["Instructor"].value_counts() if not master.empty else {}
    out = []
    for name, p in profiles.items():
        if code in p.scores and p.ftype != "Recitation Leader":
            score, basis = p.scores[code]
            out.append({"name": name, "basis": basis, "score": round(float(score), 2),
                        "assigned": int(counts.get(name, 0)), "term_target": p.term_target})
    return sorted(out, key=lambda d: (-d["score"], d["name"]))


def add_manual_sections(master: pd.DataFrame, manual: list[dict], profiles: dict[str, FacultyProfile]
                        ) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    Append scheduler-created sections to the master table. Each dict has: section_id, code,
    title, section, instructor (None = unstaffed), virtual, sequence, cap, projected.
    Returns (master, ids_added, ids_skipped); a section whose ID now collides with a
    generated section is skipped (reported as stale) rather than silently replacing it.
    """
    if not manual:
        return master, [], []
    existing = set(master["Section ID"]) if not master.empty else set()
    rows, added, skipped = [], [], []
    for ms in manual:
        if ms["section_id"] in existing:
            skipped.append(ms["section_id"])
            continue
        code = int(ms["code"])
        rows.append({
            "Section ID": ms["section_id"], "Course": f"ECON {code}", "Section": ms["section"],
            "Title": ms["title"], "Category": course_category(code), "Level": course_level(code),
            "Component": "Lecture", "Modality": "Online (Async)" if ms["virtual"] else "In-Person",
            "Section Cap": int(ms["cap"]), "Projected Enrollment": int(min(ms.get("projected", 0), ms["cap"])),
            "Instructor": ms.get("instructor") or UNSTAFFED, "Match Basis": MANUAL_BASIS,
            "Sequence": ASYNC_SLOT if ms["virtual"] else (ms.get("sequence") or UNSCHEDULED),
            "Linked Lecture": "", "Prerequisites": format_prereqs(get_prerequisites(code)),
        })
        added.append(ms["section_id"])
    if not rows:
        return master, [], skipped
    combined = pd.concat([master, pd.DataFrame(rows)], ignore_index=True) if not master.empty else pd.DataFrame(rows)
    return finalize_master(combined, profiles), added, skipped


def run_pipeline(raw_enrollment: pd.DataFrame, settings: Settings,
                 preferences_source=PREFERENCES_FILE, roster_override: pd.DataFrame | None = None, *,
                 prefs: dict | None = None, faculty: list[str] | None = None,
                 overloads: dict | None = None, catalog: dict[int, str] | None = None,
                 saved_roster: dict | None = None) -> dict:
    """
    Run demand estimation and scheduling end to end. Any input left as None is read from the
    legacy files in BASE_DIR (Streamlit prototype); the API injects DB data.
    """
    enr = load_enrollment(raw_enrollment)
    if catalog is None:
        catalog = load_catalog(enr)
    else:
        # Courses removed/deactivated in the catalog are not planned
        enr = enr[enr["course"].isin(catalog) | (enr["course"] >= 5000)].copy()
    if prefs is None:
        prefs, pref_warnings = load_preferences(preferences_source)
    else:
        pref_warnings = []
        for name, p in prefs.items():
            bad = [c for c in p["ranks"] if c not in catalog]
            if bad:
                pref_warnings.append(f"{name}: ranked course(s) not in the active catalog: "
                                     + ", ".join(f"ECON {c}" for c in bad))
                p["ranks"] = [c for c in p["ranks"] if c in catalog]

    if faculty is None:
        faculty = load_faculty_list(enr)
    for name in prefs:
        if name not in faculty:
            pref_warnings.append(f"{name} submitted a form but is not on the active faculty list.")
    roster = roster_override if roster_override is not None else infer_roster(
        enr, faculty + [n for n in prefs if n not in faculty], saved_roster)
    if overloads is None:
        overloads = load_overloads()

    requested = {c for p in prefs.values() for c in p["ranks"]}
    demand = estimate_demand(enr, settings, catalog, requested)
    sections = plan_sections(demand, settings)

    profiles = build_faculty_profiles(enr, roster, prefs, overloads, settings)
    sections, dropped = assign_instructors(sections, profiles, settings)
    sections = assign_time_slots(sections, profiles, slot_popularity(enr))

    master = sections_to_master(sections, profiles)
    offered = set(master["Course"].str.extract(r"(\d{4})")[0].astype(int)) if not master.empty else set()
    prereq = validate_prerequisites(offered, catalog)
    unseated = unseated_demand(demand)
    conflicts = detect_conflicts(master, profiles, settings, prereq, dropped, pref_warnings, unseated)
    workload = workload_summary(master, profiles, settings)

    return {
        "unseated": unseated,
        "enrollment": enr, "catalog": catalog, "prefs": prefs, "pref_warnings": pref_warnings,
        "roster": roster, "overloads": overloads, "demand": demand, "profiles": profiles,
        "master": master, "dropped": dropped, "prereq": prereq,
        "conflicts": conflicts, "workload": workload,
    }
