import streamlit as st
import pandas as pd
import numpy as np

# ==============================================================================
# 1. STANDARD NORTHEASTERN COURSE SEQUENCE TIMETABLE
# ==============================================================================
COURSE_SEQUENCES = {
    # MWR Sequences (Mon / Wed / Thu) - 65 min lectures
    "MWR_1": {"days": "MWR", "time": "08:00 AM - 09:05 AM", "label": "Seq 1 (MWR 0800-0905)"},
    "MWR_2": {"days": "MWR", "time": "09:15 AM - 10:20 AM", "label": "Seq 2 (MWR 0915-1020)"},
    "MWR_3": {"days": "MWR", "time": "10:30 AM - 11:35 AM", "label": "Seq 3 (MWR 1030-1135)"},
    "MWR_4": {"days": "MWR", "time": "01:35 PM - 02:40 PM", "label": "Seq 4 (MWR 1335-1440)"},
    "MWR_5": {"days": "MWR", "time": "04:35 PM - 05:40 PM", "label": "Seq 5 (MWR 1635-1740)"},

    # 2-Day Sequences (Tue/Fri - TF, Mon/Wed - MW, Wed/Fri - WF) - 100 min lectures
    "TF_A": {"days": "TF", "time": "08:00 AM - 09:40 AM", "label": "Seq A (TF 0800-0940)"},
    "TF_B": {"days": "TF", "time": "09:50 AM - 11:30 AM", "label": "Seq B (TF 0950-1130)"},
    "TF_C": {"days": "TF", "time": "11:45 AM - 01:25 PM", "label": "Seq C (TF 1145-1325)"},
    "TF_D": {"days": "TF", "time": "01:35 PM - 03:15 PM", "label": "Seq D (TF 1335-1515)"},
    "TF_E": {"days": "TF", "time": "03:25 PM - 05:05 PM", "label": "Seq E (TF 1525-1705)"},
    "MW_F": {"days": "MW", "time": "02:50 PM - 04:30 PM", "label": "Seq F (MW 1450-1630)"},
    "WF_G": {"days": "WF", "time": "11:45 AM - 01:25 PM", "label": "Seq G (WF 1145-1325)"},

    # Recitation / Single-day slots (Sequences L - T) - 65 min sessions
    "R_L": {"days": "R", "time": "08:00 AM - 09:05 AM", "label": "Seq L (R 0800-0905)"},
    "R_M": {"days": "R", "time": "01:35 PM - 02:40 PM", "label": "Seq M (R 1335-1440)"},
    "R_N": {"days": "R", "time": "02:50 PM - 03:55 PM", "label": "Seq N (R 1450-1555)"},
    "F_P": {"days": "F", "time": "08:00 AM - 09:05 AM", "label": "Seq P (F 0800-0905)"},
    "F_Q": {"days": "F", "time": "11:45 AM - 01:25 PM", "label": "Seq Q (F 1145-1325)"},
    "F_R": {"days": "F", "time": "02:50 PM - 03:55 PM", "label": "Seq R (F 1450-1555)"},
    "W_S": {"days": "W", "time": "01:35 PM - 02:40 PM", "label": "Seq S (W 1335-1440)"},
    "T_T": {"days": "T", "time": "02:50 PM - 03:55 PM", "label": "Seq T (T 1450-1555)"},
}


# ==============================================================================
# 2. HISTORICAL CLASS CAP CALCULATOR (2022-2026)
# ==============================================================================
def calculate_historical_caps(df):
    """
    Computes average class caps across all historical data (2022-2026)
    grouped by course code, semester type (Fall vs Spring), and modality.
    """
    clean = df[
        df["UG_ENROLLMENT"].notna() & 
        (df["UG_ENROLLMENT"] > 0) & 
        (df["Course #"] < 5000)
    ].copy()

    clean["Semester_Type"] = clean["ACADEMIC_PERIOD_DESC"].apply(
        lambda x: "Fall" if "Fall" in str(x) else ("Spring" if "Spring" in str(x) else "Other")
    )

    clean["is_virtual"] = (
        (clean["CAMPUS"] == "VTL") | 
        (clean["Instructional Method"].str.contains("Online|Virtual", case=False, na=False))
    )

    # Compute historical mean caps per (Semester_Type, is_virtual, Course #)
    cap_averages = (
        clean.groupby(["Semester_Type", "is_virtual", "Course #"])["MAXIMUM_ENROLLMENT"]
        .mean()
        .round()
        .astype(int)
        .to_dict()
    )
    
    return cap_averages


# ==============================================================================
# 3. COURSE SCHEDULER ENGINE
# ==============================================================================
def generate_semester_schedule(df, term_prefix="Fall 2026", semester_type="Fall", historical_caps={}):
    """
    Generates course schedule for undergraduate courses (< 5000 level).
    Uses 2022-2026 historical semester averages to set estimated class caps.
    Caps virtual sections at min(historical_avg, 25).
    """
    clean_df = df[
        df["UG_ENROLLMENT"].notna() & 
        (df["UG_ENROLLMENT"] > 0) & 
        (df["Course #"] < 5000)
    ].copy()

    term_df = clean_df[clean_df["ACADEMIC_PERIOD_DESC"].str.contains(term_prefix, na=False)].copy()
    if term_df.empty:
        term_df = clean_df[clean_df["ACADEMIC_PERIOD_DESC"].str.contains(semester_type, na=False)].copy()

    term_df["is_virtual"] = (
        (term_df["CAMPUS"] == "VTL") | 
        (term_df["Instructional Method"].str.contains("Online|Virtual", case=False, na=False))
    )

    section_rows = []
    
    lecture_seqs = ["MWR_2", "MWR_3", "MWR_4", "TF_B", "TF_C", "TF_D", "MW_F", "WF_G", "MWR_1", "TF_A", "TF_E"]
    recitation_seqs = ["R_L", "R_M", "R_N", "F_P", "F_Q", "F_R", "W_S", "T_T"]

    seq_idx = 0
    rec_idx = 0

    for idx, row in term_df.iterrows():
        code = int(row["Course #"])
        title = str(row["Course Title"])
        crn = int(row["CRN"]) if not np.isnan(row["CRN"]) else "N/A"
        is_vrtl = row["is_virtual"]

        # --- DYNAMIC CAP DETERMINATION ---
        if is_vrtl:
            # Look up historical average for this virtual course
            vrtl_hist_cap = historical_caps.get((semester_type, True, code), 25)
            # Retain historical average if lower than 25 (e.g. 19), otherwise cap at 25
            estimated_cap = min(vrtl_hist_cap, 25)
        else:
            # On-campus historical lookup
            estimated_cap = historical_caps.get((semester_type, False, code), 40)

        # Assign Timetable / Sequence
        if is_vrtl:
            seq_label = "Asynchronous (VRTL)"
            days = "Async"
            time_slot = "No Fixed Meeting Time"
        else:
            if "Recitation" in title or code in [1125, 1126]:
                seq_key = recitation_seqs[rec_idx % len(recitation_seqs)]
                rec_idx += 1
            else:
                seq_key = lecture_seqs[seq_idx % len(lecture_seqs)]
                seq_idx += 1

            seq_info = COURSE_SEQUENCES[seq_key]
            seq_label = seq_info["label"]
            days = seq_info["days"]
            time_slot = seq_info["time"]

        section_rows.append({
            "CRN": crn,
            "Course Code": f"ECON {code}",
            "Course Title": title,
            "Modality": "Virtual (Async)" if is_vrtl else "On-Campus",
            "Estimated Class Cap": estimated_cap,
            "Sequence Slot": seq_label,
            "Days": days,
            "Meeting Time": time_slot,
        })

    return pd.DataFrame(section_rows)


# ==============================================================================
# 4. STREAMLIT DELIVERABLE INTERFACE
# ==============================================================================
def render_course_scheduler_page():
    st.title("📅 Undergraduate Course Offerings & Timetable Scheduler")
    st.caption("Generates projected undergraduate section offerings (< 5000 level) with estimated class caps derived from 2022–2026 historical semester averages.")

    try:
        df = pd.read_excel("ECON_Enrollment.xlsx")
    except Exception as e:
        st.error(f"Error loading `ECON_Enrollment.xlsx`: {e}")
        return

    # Compute 2022-2026 historical class cap averages per semester & modality
    historical_caps = calculate_historical_caps(df)

    tab_fall, tab_spring = st.tabs(["🍂 Fall Semester Offerings", "🌸 Spring Semester Offerings"])

    # --- FALL SEMESTER TAB ---
    with tab_fall:
        st.subheader("Fall Semester Course Schedule")
        fall_df = generate_semester_schedule(
            df, 
            term_prefix="Fall 2026", 
            semester_type="Fall", 
            historical_caps=historical_caps
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Unique Courses Offered", fall_df["Course Code"].nunique())
        c2.metric("Total Sections Offered", len(fall_df))
        c3.metric("On-Campus Sections", len(fall_df[fall_df["Modality"] == "On-Campus"]))
        c4.metric("Virtual Sections (Async)", len(fall_df[fall_df["Modality"] != "On-Campus"]))

        st.dataframe(
            fall_df,
            column_config={
                "CRN": st.column_config.NumberColumn("CRN", format="%d", width="small"),
                "Course Code": st.column_config.TextColumn("Course Code", width="small"),
                "Course Title": st.column_config.TextColumn("Course Title", width="large"),
                "Modality": st.column_config.TextColumn("Modality", width="small"),
                "Estimated Class Cap": st.column_config.NumberColumn("Estimated Class Cap (2022-26 Avg)", format="%d seats"),
                "Sequence Slot": st.column_config.TextColumn("Sequence Slot"),
                "Days": st.column_config.TextColumn("Days"),
                "Meeting Time": st.column_config.TextColumn("Meeting Time"),
            },
            hide_index=True,
            use_container_width=True
        )

        csv_fall = fall_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Fall Schedule (CSV)", csv_fall, "fall_undergrad_schedule.csv", "text/csv")

    # --- SPRING SEMESTER TAB ---
    with tab_spring:
        st.subheader("Spring Semester Course Schedule")
        spring_df = generate_semester_schedule(
            df, 
            term_prefix="Spring 2026", 
            semester_type="Spring", 
            historical_caps=historical_caps
        )

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Unique Courses Offered", spring_df["Course Code"].nunique())
        s2.metric("Total Sections Offered", len(spring_df))
        s3.metric("On-Campus Sections", len(spring_df[spring_df["Modality"] == "On-Campus"]))
        s4.metric("Virtual Sections (Async)", len(spring_df[spring_df["Modality"] != "On-Campus"]))

        st.dataframe(
            spring_df,
            column_config={
                "CRN": st.column_config.NumberColumn("CRN", format="%d", width="small"),
                "Course Code": st.column_config.TextColumn("Course Code", width="small"),
                "Course Title": st.column_config.TextColumn("Course Title", width="large"),
                "Modality": st.column_config.TextColumn("Modality", width="small"),
                "Estimated Class Cap": st.column_config.NumberColumn("Estimated Class Cap (2022-26 Avg)", format="%d seats"),
                "Sequence Slot": st.column_config.TextColumn("Sequence Slot"),
                "Days": st.column_config.TextColumn("Days"),
                "Meeting Time": st.column_config.TextColumn("Meeting Time"),
            },
            hide_index=True,
            use_container_width=True
        )

        csv_spring = spring_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Spring Schedule (CSV)", csv_spring, "spring_undergrad_schedule.csv", "text/csv")


if __name__ == "__main__":
    render_course_scheduler_page()