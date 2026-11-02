import streamlit as st
import pandas as pd
import numpy as np
import math

# ==============================================================================
# 1. CORE ECONOMICS DEFINITIONS
# ==============================================================================
CORE_COURSES = {1115, 1116, 1125, 1126, 2315, 2316, 2350, 4697, 4698}


# ==============================================================================
# 2. HISTORICAL & DYNAMIC CLASS CAP CALCULATOR
# ==============================================================================
def calculate_historical_caps(df):
    """
    Computes average class caps across all loaded historical data 
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

    cap_averages = (
        clean.groupby(["Semester_Type", "is_virtual", "Course #"])["MAXIMUM_ENROLLMENT"]
        .mean()
        .round()
        .astype(int)
        .to_dict()
    )
    
    return cap_averages


# ==============================================================================
# 3. FACULTY PREFERENCE & MATCHING ENGINE
# ==============================================================================
def load_teacher_preferences(csv_path="teacher_preferences.csv"):
    try:
        pref_df = pd.read_csv(csv_path)
        if pref_df.empty:
            return {}
        
        pref_map = {}
        for _, row in pref_df.iterrows():
            name = str(row.get("Full Name", "")).strip()
            if not name:
                continue
            
            ranked_courses = []
            for col in ["Rank 1 Course", "Rank 2 Course", "Rank 3 Course", "Rank 4 Course", "Rank 5 Course", "Rank 6 Course"]:
                val = str(row.get(col, ""))
                digits = "".join(filter(str.isdigit, val))
                if digits:
                    ranked_courses.append(int(digits))

            pref_map[name] = {
                "fall_target": int(row.get("Fall Desired Courses", 2)),
                "spring_target": int(row.get("Spring Desired Courses", 2)),
                "preferred_courses": ranked_courses,
            }
        return pref_map
    except Exception:
        return {}


# ==============================================================================
# 4. SIMPLIFIED SECTION & RECITATION ESTIMATION ENGINE
# ==============================================================================
def generate_curriculum_summary(df, pref_map, target_term="Fall 2026", growth_multiplier=1.00, historical_caps={}):
    """
    Aggregates courses by course code and modality. Determines total required sections, 
    estimated class capacities, and accurately scales recitations based on total 
    lecture enrollment and recitation size caps.
    """
    semester_type = "Fall" if "Fall" in target_term else "Spring"

    clean_df = df[
        df["UG_ENROLLMENT"].notna() & 
        (df["UG_ENROLLMENT"] > 0) & 
        (df["Course #"] < 5000) &
        ~df["Course #"].isin([1125, 1126]) # Recitations handled dynamically from lectures
    ].copy()

    term_df = clean_df[clean_df["ACADEMIC_PERIOD_DESC"].str.contains(target_term, na=False)].copy()
    if term_df.empty:
        # Fallback to representative semester type if exact term not found
        clean_df["Semester_Type"] = clean_df["ACADEMIC_PERIOD_DESC"].apply(
            lambda x: "Fall" if "Fall" in str(x) else ("Spring" if "Spring" in str(x) else "Other")
        )
        term_df = clean_df[clean_df["Semester_Type"] == semester_type].drop_duplicates(subset=["Course #"])

    term_df["is_virtual"] = (
        (term_df["CAMPUS"] == "VTL") | 
        (term_df["Instructional Method"].str.contains("Online|Virtual", case=False, na=False))
    )

    # Group by course and modality to determine section counts and total expected students
    summary_rows = []
    
    # Track macro/micro lecture enrollments for recitation calculation
    macro_total_students = 0
    micro_total_students = 0

    grouped = term_df.groupby(["Course #", "Course Title", "is_virtual"])

    for (code, title, is_vrtl), group in grouped:
        num_sections = len(group)
        
        # Calculate projected cap per section
        if is_vrtl:
            vrtl_hist_cap = historical_caps.get((semester_type, True, code), 25)
            estimated_cap = int(min(vrtl_hist_cap * growth_multiplier, 25))
        else:
            base_cap = int(group["MAXIMUM_ENROLLMENT"].mean()) if not group["MAXIMUM_ENROLLMENT"].empty else 40
            estimated_cap = int(round(base_cap * growth_multiplier))

        total_enrolled_est = int(group["UG_ENROLLMENT"].sum() * growth_multiplier)

        if code == 1115 and not is_vrtl:
            macro_total_students += total_enrolled_est
        elif code == 1116 and not is_vrtl:
            micro_total_students += total_enrolled_est

        modality_label = "Asynchronous (Virtual)" if is_vrtl else "Synchronous (On-Campus)"
        is_core = code in CORE_COURSES

        summary_rows.append({
            "Course Code": f"ECON {code}",
            "Course Title": title,
            "Core?": "Yes" if is_core else "No",
            "Modality": modality_label,
            "Required Sections": num_sections,
            "Estimated Class Cap": estimated_cap,
            "Total Projected Enrollment": total_enrolled_est,
        })

    summary_df = pd.DataFrame(summary_rows)

    # --- RECITATION DYNAMIC CALCULATION ---
    # Recitations are required for Principles of Macroeconomics (1115) and Microeconomics (1116) on-campus lectures
    recitation_rows = []
    recitation_cap = 30 # Standard recitation cap

    if macro_total_students > 0:
        macro_rec_sections = math.ceil(macro_total_students / recitation_cap)
        recitation_rows.append({
            "Course Code": "ECON 1125",
            "Course Title": "Recitation for ECON 1115",
            "Core?": "Yes",
            "Modality": "Synchronous (On-Campus)",
            "Required Sections": macro_rec_sections,
            "Estimated Class Cap": recitation_cap,
            "Total Projected Enrollment": macro_total_students,
        })

    if micro_total_students > 0:
        micro_rec_sections = math.ceil(micro_total_students / recitation_cap)
        recitation_rows.append({
            "Course Code": "ECON 1126",
            "Course Title": "Recitation for ECON 1116",
            "Core?": "Yes",
            "Modality": "Synchronous (On-Campus)",
            "Required Sections": micro_rec_sections,
            "Estimated Class Cap": recitation_cap,
            "Total Projected Enrollment": micro_total_students,
        })

    if recitation_rows:
        summary_df = pd.concat([summary_df, pd.DataFrame(recitation_rows)], ignore_index=True)

    return summary_df.sort_values(by=["Core?", "Course Code"], ascending=[False, True])


# ==============================================================================
# 5. STREAMLIT USER INTERFACE
# ==============================================================================
def render_course_scheduler_page():
    st.set_page_config(page_title="Course Curriculum & Section Estimator", page_icon="📚", layout="wide")
    st.title("📚 Undergraduate Course Curriculum & Section Estimator")
    st.caption("Clean summary of required course sections, modalities (Sync/Async), capacities, and dynamically calculated recitations.")

    # Sidebar Settings
    st.sidebar.header("⚙️ Simulation & Term Settings")
    
    target_term = st.sidebar.selectbox(
        "Select Target / Future Semester",
        ["Fall 2026", "Spring 2027", "Fall 2027", "Spring 2028", "Fall 2028", "Custom Term"]
    )
    
    if target_term == "Custom Term":
        target_term = st.sidebar.text_input("Enter Custom Semester Name", "Fall 2029")

    growth_multiplier = st.sidebar.slider(
        "📈 Enrollment Growth Multiplier",
        min_value=0.85, max_value=1.50, value=1.00, step=0.05,
        help="Scales student enrollment counts and section requirements upward or downward."
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("📂 Add New Semester Data")
    uploaded_file = st.sidebar.file_uploader("Upload additional Excel/CSV historical records", type=["xlsx", "csv"])

    # Load data
    try:
        df = pd.read_excel("ECON_Enrollment.xlsx")
    except Exception as e:
        st.error(f"Error loading baseline `ECON_Enrollment.xlsx`: {e}")
        return

    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(".csv"):
                new_data = pd.read_csv(uploaded_file)
            else:
                new_data = pd.read_excel(uploaded_file)
            df = pd.concat([df, new_data], ignore_index=True)
            st.sidebar.success(f"Successfully merged {len(new_data)} records!")
        except Exception as e:
            st.sidebar.error(f"Error reading uploaded file: {e}")

    historical_caps = calculate_historical_caps(df)
    pref_map = load_teacher_preferences("teacher_preferences.csv")

    # Generate Summary Table
    curriculum_df = generate_curriculum_summary(
        df, 
        pref_map,
        target_term=target_term, 
        growth_multiplier=growth_multiplier,
        historical_caps=historical_caps
    )

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Unique Courses Offered", curriculum_df["Course Code"].nunique())
    c2.metric("Total Sections Required", int(curriculum_df["Required Sections"].sum()))
    c3.metric("Synchronous Sections", int(curriculum_df[curriculum_df["Modality"].str.contains("Synchronous")]["Required Sections"].sum()))
    c4.metric("Asynchronous Sections", int(curriculum_df[curriculum_df["Modality"].str.contains("Asynchronous")]["Required Sections"].sum()))

    st.markdown(f"### Master Curriculum & Section Plan ({target_term})")
    st.markdown("All CRNs, scheduling times, and sequence slots have been removed. Below is the clean section count and modality breakdown, with recitations automatically scaled to match total lecture enrollment.")

    edited_df = st.data_editor(
        curriculum_df,
        column_config={
            "Course Code": st.column_config.TextColumn("Course Code", width="small"),
            "Course Title": st.column_config.TextColumn("Course Title", width="large"),
            "Core?": st.column_config.TextColumn("Core?", width="small"),
            "Modality": st.column_config.TextColumn("Modality", width="medium"),
            "Required Sections": st.column_config.NumberColumn("Required Sections", format="%d sections", width="small"),
            "Estimated Class Cap": st.column_config.NumberColumn("Estimated Class Cap", format="%d seats", width="small"),
            "Total Projected Enrollment": st.column_config.NumberColumn("Projected Students", format="%d students", width="small"),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic"
    )

    csv_data = edited_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"📥 Download Curriculum Summary ({target_term}) as CSV",
        data=csv_data,
        file_name=f"curriculum_summary_{target_term.replace(' ', '_').lower()}.csv",
        mime="text/csv"
    )


if __name__ == "__main__":
    render_course_scheduler_page()