"""
COURSE_SCHEDULER.py
===================
Streamlit UI for the Northeastern University Department of Economics
Automated Course Scheduler (undergraduate only).

    streamlit run COURSE_SCHEDULER.py

Demand & Sections   — projected demand, section counts, recitations, prerequisites
Master Curriculum   — instructor matching + sequence/time-slot assignment (editable)
          Unresolved Conflicts — unstaffed core, workload violations, schedule overlaps
          Faculty Workload     — load vs. contract and faculty_overloads.json
          Sequence Grid        — how sections are spread over Course_Sequences.pdf blocks
          Faculty Roster       — confirm faculty groups / reductions (faculty_roster.json)

All planning logic lives in scheduler_engine.py; this file only handles UI.
"""

from __future__ import annotations

import hashlib
import io
import os

import pandas as pd
import streamlit as st

import scheduler_engine as eng

st.set_page_config(page_title="ECON Course Scheduler", page_icon="📚", layout="wide")

SEVERITY_ICON = {"Critical": "🔴 Critical", "Warning": "🟠 Warning", "Info": "🔵 Info"}


# ==============================================================================
# 1. DATA LOADING (cached)
# ==============================================================================
def _mtime(path: str) -> float:
    return os.path.getmtime(path) if os.path.exists(path) else 0.0


@st.cache_data(show_spinner=False)
def load_base_enrollment(mtime: float) -> pd.DataFrame:
    return pd.read_excel(eng.ENROLLMENT_FILE)


@st.cache_data(show_spinner="Running scheduler…")
def cached_pipeline(raw: pd.DataFrame, settings_items: tuple, file_stamp: tuple) -> dict:
    # file_stamp is only part of the cache key so edits to the JSON/CSV inputs re-run the engine
    return eng.run_pipeline(raw, eng.Settings(**dict(settings_items)))


def read_upload(uploaded) -> pd.DataFrame:
    if uploaded.name.lower().endswith(".csv"):
        return pd.read_csv(uploaded)
    return pd.read_excel(uploaded)


def to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_excel(sheets: dict[str, pd.DataFrame]) -> bytes | None:
    try:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            for name, df in sheets.items():
                df.to_excel(xw, sheet_name=name[:31], index=False)
        return buf.getvalue()
    except Exception:
        return None


def public(df: pd.DataFrame) -> pd.DataFrame:
    """Drop engine-internal columns (prefixed with '_')."""
    return df[[c for c in df.columns if not str(c).startswith("_")]]


# ==============================================================================
# 2. SIDEBAR
# ==============================================================================
st.title("📚 ECON Undergraduate Course Scheduler")
st.caption("Northeastern University · Department of Economics · demand forecasting, faculty matching, "
           "sequence assignment and conflict detection (undergraduate courses only — no 5000+).")

try:
    raw = load_base_enrollment(_mtime(eng.ENROLLMENT_FILE))
except Exception as e:  # noqa: BLE001 — surface any read problem to the user
    st.error(f"Could not load `ECON_Enrollment.xlsx`: {e}")
    st.stop()

with st.sidebar:
    st.header("⚙️ Planning Settings")

    st.subheader("📂 Historical Data")
    uploaded = st.file_uploader("Merge additional enrollment records (.xlsx/.csv)", type=["xlsx", "csv"])
    if uploaded is not None:
        try:
            extra = read_upload(uploaded)
            missing = eng.validate_enrollment_columns(extra)
            if missing:
                st.error("Upload is missing columns: " + ", ".join(missing))
            else:
                raw = pd.concat([raw, extra], ignore_index=True)
                st.success(f"Merged {len(extra)} records.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read upload: {e}")

    # Term options: upcoming terms after the latest data, plus past terms for back-testing
    parsed = raw["ACADEMIC_PERIOD_DESC"].dropna().map(eng.parse_term_label)
    known = sorted({p for p in parsed if p[0]}, key=lambda p: eng.term_ordinal(*p))
    latest_ord = eng.term_ordinal(*known[-1]) if known else eng.term_ordinal("Fall", 2026)
    upcoming = []
    for k in range(1, 5):
        o = latest_ord + k
        upcoming.append(f"{'Fall' if o % 2 else 'Spring'} {o // 2}")
    backtest = [f"{s} {y} (back-test)" for s, y in reversed(known)]
    choice = st.selectbox("Target semester", upcoming + backtest + ["Custom…"])
    if choice == "Custom…":
        choice = st.text_input("Custom term (e.g. 'Fall 2029')", "Fall 2029")
    target_term = choice.replace(" (back-test)", "")
    if eng.parse_term_label(target_term)[0] is None:
        st.error("Enter a term like 'Fall 2029' or 'Spring 2030'.")
        st.stop()

    st.subheader("📈 Demand")
    growth = st.slider("Enrollment growth multiplier", 0.80, 1.50, 1.00, 0.05,
                       help="Scales projected student demand (not section caps).")
    window = st.slider("History window (same-semester terms)", 1, 5, 3)
    trend = st.checkbox("Apply historical enrollment trend", True,
                        help="Linear trend over the window, clipped to ±10%/yr.")
    min_elective = st.number_input("Min. students to run an elective", 0, 40, 15)

    st.subheader("🏫 Section Sizes")
    large_cap = st.number_input("Large lecture cap (Principles)", 100, 300, 200, 10)
    small_cap = st.number_input("Small section cap", 30, 60, 45)
    virtual_cap = st.number_input("Remote section cap (max 25)", 10, eng.VIRTUAL_CAP_LIMIT, eng.VIRTUAL_CAP_LIMIT)
    rec_cap = st.number_input("Recitation cap", 15, 60, 30)

    st.subheader("🧑‍🏫 Matching")
    fallback = st.checkbox("Use teaching history when no form was submitted", True,
                           help="Faculty without a preference form are matched to courses they have taught before.")
    force = st.checkbox("Force-fill unstaffed core sections", False,
                        help="Assign any faculty with spare capacity to core sections nobody requested (flagged for review).")
    rec_load = st.number_input("Default recitations per leader", 1, 10, 5)

settings = eng.Settings(
    target_term=target_term, growth_multiplier=growth, history_window=window, apply_trend=trend,
    large_lecture_cap=int(large_cap), small_section_cap=int(small_cap), virtual_cap=int(virtual_cap),
    recitation_cap=int(rec_cap), min_elective_demand=int(min_elective), history_fallback=fallback,
    force_fill_core=force, recitation_leader_load=int(rec_load),
)
settings_items = tuple(sorted(vars(settings).items()))
file_stamp = tuple(_mtime(p) for p in (eng.PREFERENCES_FILE, eng.OVERLOADS_FILE, eng.FACULTY_FILE,
                                       eng.ROSTER_FILE, eng.COURSES_FILE))

try:
    res = cached_pipeline(raw, settings_items, file_stamp)
except ValueError as e:
    st.error(str(e))
    st.stop()
except Exception as e:  # noqa: BLE001
    st.exception(e)
    st.stop()

profiles = res["profiles"]
sem, _ = settings.target

# --- Input status banner ---------------------------------------------------------
n_forms = len(res["prefs"])
if n_forms:
    st.success(f"Loaded **{n_forms}** faculty preference submission(s) from `teacher_preferences.csv`.")
else:
    st.info("`teacher_preferences.csv` has no submissions yet. "
            + ("Faculty are matched using their **teaching history** (sidebar option)." if fallback
               else "History fallback is off, so only core recitations/forced assignments can be staffed."))
if (res["roster"]["Source"] == "Inferred from history").any():
    st.caption("ℹ️ Some faculty groups (Tenured Track / Tenured / Full-Time / Temporary / Adjunct) are inferred from teaching "
               "history. Confirm them in the **Faculty Roster** tab.")

tabs = st.tabs(["📈 Demand & Sections", "🗂️ Master Curriculum",
                "⚠️ Unresolved Conflicts", "👥 Faculty Workload", "🗓️ Sequence Grid", "⚙️ Faculty Roster"])

# ==============================================================================
# 3. DEMAND & SECTIONS
# ==============================================================================
with tabs[0]:
    demand = res["demand"]
    planned = demand[demand["Planned Sections"] > 0]
    lec = planned[planned["Category"] != "Recitation"]
    recs = planned[planned["Category"] == "Recitation"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Courses planned", lec["_code"].nunique())
    c2.metric("Lecture sections", int(lec["Planned Sections"].sum()))
    c3.metric("Recitation sections", int(recs["Planned Sections"].sum()))
    c4.metric("Projected lecture seats", f"{int(lec['Projected Enrollment'].sum()):,}")
    c5.metric("Remote sections", int(lec.loc[lec["_virtual"], "Planned Sections"].sum()))

    st.markdown(f"### Projected Demand & Section Plan — {target_term}")
    st.caption("Projection = recency-weighted average of prior same-semester terms × clipped annual trend × "
               "growth multiplier. Principles use large lectures plus small sections; remote sections are capped "
               f"at {settings.virtual_cap}; recitations = ⌈in-person lecture students ÷ {settings.recitation_cap}⌉. "
               "Electives below the minimum demand are not planned. Electives are only *offered* if a faculty member "
               "is matched to them on the Master Curriculum tab.")
    show = public(demand).copy()
    show["Annual Trend"] = (show["Annual Trend"] * 100).round(1)
    show["Seat Fill %"] = (show["Seat Fill %"] * 100).round(0)
    only_planned = st.toggle("Show only courses with planned sections", value=False)
    if only_planned:
        show = show[show["Planned Sections"] > 0]
    st.dataframe(show, hide_index=True, width="stretch", column_config={
        "Annual Trend": st.column_config.NumberColumn("Annual Trend", format="%.1f%%"),
        "Seat Fill %": st.column_config.ProgressColumn("Seat Fill", format="%d%%", min_value=0, max_value=100),
        "Projected Enrollment": st.column_config.NumberColumn(format="%d"),
    })
    st.download_button("📥 Download demand estimate (CSV)", to_csv(show),
                       f"demand_estimate_{target_term.replace(' ', '_').lower()}.csv", "text/csv")

    st.markdown("### Prerequisite Validation")
    st.caption("1000-level: none · 3000-level: requires principles · 4000-level: multiple prerequisites incl. "
               "theory. Also checks that each prerequisite is offered this term so the pathway stays open.")
    prereq = res["prereq"]
    if prereq.empty:
        st.write("No courses to validate.")
    else:
        bad = int((~prereq["_ok"]).sum())
        (st.warning if bad else st.success)(f"{len(prereq) - bad} of {len(prereq)} offered courses pass all checks.")
        st.dataframe(public(prereq), hide_index=True, width="stretch")

# ==============================================================================
# 4. MASTER CURRICULUM (editable)
# ==============================================================================
with tabs[1]:
    base_master = res["master"]
    st.markdown(f"### Master Undergraduate Curriculum — {target_term}")
    st.caption("Core courses are staffed first, then recitations, then electives (an elective is offered only "
               "when a willing instructor has capacity). Lectures use class sequences 1–5 / A–H; recitations use "
               "65-minute slots inside lab sequences L–W and never overlap their linked lecture.")

    edit_mode = st.toggle("✏️ Manual adjustments (change instructor or sequence; conflicts re-check live)")
    master = base_master
    if edit_mode and not base_master.empty:
        editor_key = "master_editor_" + hashlib.md5(repr((settings_items, file_stamp)).encode()).hexdigest()[:10]
        editable_cols = ["Section ID", "Course", "Title", "Component", "Modality", "Instructor", "Sequence"]
        instructor_opts = sorted(profiles) + [eng.UNSTAFFED, eng.RECITATION_TBA]
        seq_opts = list(eng.CLASS_SEQUENCES) + list(eng.LAB_SEQUENCES) + list(eng.RECITATION_SLOTS) + [
            eng.ASYNC_SLOT, eng.UNSCHEDULED]
        edited = st.data_editor(
            base_master[editable_cols], key=editor_key, hide_index=True, width="stretch",
            disabled=["Section ID", "Course", "Title", "Component", "Modality"],
            column_config={
                "Instructor": st.column_config.SelectboxColumn("Instructor", options=instructor_opts, required=True),
                "Sequence": st.column_config.SelectboxColumn("Sequence", options=seq_opts, required=True),
            },
        )
        merged = base_master.copy()
        changed = (merged["Instructor"] != edited["Instructor"]) | (merged["Sequence"] != edited["Sequence"])
        merged["Instructor"] = edited["Instructor"].values
        merged["Sequence"] = edited["Sequence"].values
        merged.loc[changed, "Match Basis"] = "Manual override"
        master = eng.finalize_master(merged, profiles)
        if changed.any():
            st.info(f"{int(changed.sum())} section(s) manually changed. The tables below and the conflict / "
                    "workload tabs reflect your edits.")

    if master.empty:
        st.warning("No sections were planned for this term.")
    else:
        staffed = ~master["Instructor"].isin([eng.UNSTAFFED, eng.RECITATION_TBA])
        core_mask = master["Category"].str.startswith("Core")
        pref_mask = master["Match Basis"].str.contains("Rank [1-3]|Principles", regex=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sections", len(master))
        c2.metric("Core sections staffed", f"{int((staffed & core_mask).sum())}/{int(core_mask.sum())}")
        c3.metric("Electives offered", master.loc[master["Category"] == "Elective", "Course"].nunique())
        c4.metric("Top-3 / principles preference matches", int(pref_mask.sum()))

        filt = st.multiselect("Filter by category", sorted(master["Category"].unique()), placeholder="All categories")
        view = master[master["Category"].isin(filt)] if filt else master
        st.dataframe(view, hide_index=True, width="stretch", height=520)

    st.download_button("📥 Download master curriculum (CSV)", to_csv(master),
                       f"master_curriculum_{target_term.replace(' ', '_').lower()}.csv", "text/csv",
                       disabled=master.empty)

# Conflicts & workload are always computed from the (possibly edited) master table
conflicts = eng.detect_conflicts(master, profiles, settings, res["prereq"], res["dropped"], res["pref_warnings"])
workload = eng.workload_summary(master, profiles, settings)

# ==============================================================================
# 5. UNRESOLVED CONFLICTS
# ==============================================================================
with tabs[2]:
    st.markdown(f"### Unresolved Conflicts Report — {target_term}")
    if conflicts.empty:
        st.success("No conflicts detected. 🎉")
    else:
        counts = conflicts["Severity"].value_counts()
        c1, c2, c3 = st.columns(3)
        c1.metric("🔴 Critical", int(counts.get("Critical", 0)))
        c2.metric("🟠 Warnings", int(counts.get("Warning", 0)))
        c3.metric("🔵 Info", int(counts.get("Info", 0)))
        sev = st.multiselect("Severity", ["Critical", "Warning", "Info"], default=["Critical", "Warning"])
        cats = st.multiselect("Category", sorted(conflicts["Category"].unique()), placeholder="All categories")
        view = conflicts[conflicts["Severity"].isin(sev)]
        if cats:
            view = view[view["Category"].isin(cats)]
        view = view.assign(Severity=view["Severity"].map(SEVERITY_ICON))
        st.dataframe(view, hide_index=True, width="stretch", height=480)
    st.download_button("📥 Download conflicts report (CSV)", to_csv(conflicts),
                       f"unresolved_conflicts_{target_term.replace(' ', '_').lower()}.csv", "text/csv",
                       disabled=conflicts.empty)

# ==============================================================================
# 6. FACULTY WORKLOAD
# ==============================================================================
with tabs[3]:
    st.markdown(f"### Faculty Workload — {target_term}")
    st.caption("Annual load = sections assigned this term + planned load for the other semester (from the form, "
               "or teaching history). Contracts: Tenured Track / Tenured 3/yr (may teach fewer) · Full-Time Teaching 6/yr · "
               "Temporary 6/yr · Adjunct 1–2/yr. Approved overloads in `faculty_overloads.json` raise the "
               "ceiling (extra compensation); roster reductions (grad teaching, buyouts, sabbatical) lower it.")
    if workload.empty:
        st.write("No faculty with load this term.")
    else:
        types = st.multiselect("Faculty group", list(eng.FACULTY_TYPES), placeholder="All groups")
        wl_view = workload[workload["Type"].isin(types)] if types else workload
        st.dataframe(wl_view, hide_index=True, width="stretch", height=520)
    st.download_button("📥 Download workload report (CSV)", to_csv(workload),
                       f"faculty_workload_{target_term.replace(' ', '_').lower()}.csv", "text/csv",
                       disabled=workload.empty)

# ==============================================================================
# 7. SEQUENCE GRID
# ==============================================================================
with tabs[4]:
    st.markdown("### Sections per Sequence (Course_Sequences.pdf)")
    if master.empty:
        st.write("Nothing scheduled.")
    else:
        rows = []
        for code in list(eng.CLASS_SEQUENCES) + list(eng.RECITATION_SLOTS) + [eng.ASYNC_SLOT, eng.UNSCHEDULED]:
            secs = master[master["Sequence"] == code]
            if secs.empty and code not in eng.CLASS_SEQUENCES:
                continue
            days, time = eng.describe_slot(code)
            rows.append({"Sequence": code, "Type": eng.slot_type(code), "Days": days, "Time": time,
                         "Sections": len(secs), "Courses": ", ".join(secs["Section ID"].tolist())})
        grid = pd.DataFrame(rows)
        st.dataframe(grid, hide_index=True, width="stretch", height=560, column_config={
            "Sections": st.column_config.ProgressColumn("Sections", format="%d", min_value=0,
                                                        max_value=int(grid["Sections"].max() or 1)),
        })

# ==============================================================================
# 8. FACULTY ROSTER
# ==============================================================================
with tabs[5]:
    st.markdown("### Faculty Roster & Groups")
    st.caption("Faculty group drives the workload rules. Rows marked *Inferred from history* are a starting guess "
               "— correct them and click **Save** (writes `faculty_roster.json`). *Annual Reduction* covers grad "
               "teaching, joint appointments, buyouts or sabbaticals.")
    roster = res["roster"]
    edited_roster = st.data_editor(
        roster, hide_index=True, width="stretch", key="roster_editor",
        disabled=["Faculty", "UG Lectures / Yr (hist.)", "Grad Sections / Yr (hist.)", "Source"],
        column_config={
            "Type": st.column_config.SelectboxColumn("Type", options=list(eng.FACULTY_TYPES), required=True),
            "Annual Reduction": st.column_config.NumberColumn("Annual Reduction", min_value=0, max_value=6, step=1),
        },
    )
    if st.button("💾 Save roster", type="primary"):
        try:
            eng.save_roster(edited_roster)
            st.success("Saved `faculty_roster.json`. Re-running the scheduler…")
            st.rerun()
        except OSError as e:
            st.error(f"Could not save roster: {e}")

    st.markdown("#### Overload Records (`faculty_overloads.json`)")
    ov = res["overloads"]
    approved = {k: v for k, v in ov.items() if v.get("overloading")}
    if approved:
        st.dataframe(pd.DataFrame([{"Faculty": k, "Semester": v.get("semester")} for k, v in approved.items()]),
                     hide_index=True)
    else:
        st.write("No approved overloads. Manage them in the TEACHER_PREFERENCES.py admin panel.")

    st.markdown("#### Preference Submissions (`teacher_preferences.csv`)")
    if res["prefs"]:
        st.dataframe(pd.DataFrame([{
            "Faculty": n, "Ranked Courses": ", ".join(f"ECON {c}" for c in p["ranks"]),
            "Principles": ", ".join(f"ECON {c}" for c in p["principles"]),
            "Fall": p["Fall"], "Spring": p["Spring"],
            "Overload": p["overload_semester"] if p["overload"] else "No",
            "Unique Circumstances": p["circumstances"],
        } for n, p in res["prefs"].items()]), hide_index=True, width="stretch")
    else:
        st.write("No submissions yet — faculty submit via `streamlit run TEACHER_PREFERENCES.py`.")

# ==============================================================================
# 9. FULL EXPORT
# ==============================================================================
st.divider()
xlsx = to_excel({
    "Master Curriculum": master, "Unresolved Conflicts": conflicts, "Faculty Workload": workload,
    "Demand Estimate": public(res["demand"]), "Prerequisites": public(res["prereq"]),
})
if xlsx:
    st.download_button("📦 Download full planning workbook (.xlsx)", xlsx,
                       f"econ_schedule_{target_term.replace(' ', '_').lower()}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
