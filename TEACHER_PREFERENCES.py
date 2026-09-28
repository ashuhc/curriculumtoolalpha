import os
import pandas as pd
import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="Faculty Teaching Preferences Form",
    page_icon="🎓",
    layout="centered"
)

CSV_FILE = "teacher_preferences.csv"

# HARDCODED ADMIN PASSWORD
ADMIN_PASSWORD = "econpassword123"

# Header Section
st.title("🎓 Faculty Teaching Preferences Form")
st.markdown(
    """
    Please fill out your teaching preferences for the upcoming academic year. 
    Refer to the [Northeastern Undergraduate Economics Course Catalog](https://catalog.northeastern.edu/undergraduate/social-sciences-humanities/economics/#coursestext) for course codes and titles.
    """
)

# -----------------------------------------------------------------------------
# 1. FACULTY FORM
# -----------------------------------------------------------------------------
with st.form("preference_form", clear_on_submit=True):
    
    st.subheader("1. Contact Information")
    col1, col2 = st.columns(2)
    with col1:
        full_name = st.text_input("Full Name*", placeholder="e.g., Dr. Jane Doe")
    with col2:
        email = st.text_input("Northeastern Email*", placeholder="e.g., j.doe@northeastern.edu")

    st.markdown("---")

    st.subheader("2. Principles Course Preferences")
    principles_prefs = st.multiselect(
        "Which Principles courses would you prefer to teach? (Select all that apply)",
        options=[
            "ECON 1115 - Principles of Macroeconomics",
            "ECON 1116 - Principles of Microeconomics",
            "ECON 2350 - Statistics for Economists",
            "None / Not Applicable"
        ]
    )

    st.markdown("---")

    st.subheader("3. Top 6 Undergraduate Course Preferences")
    st.caption("Rank your top 6 course choices. Please include both the **Course Code** and **Course Title** (e.g., *ECON 3410 - Microeconomic Theory*).")

    ranked_courses = []
    for i in range(1, 7):
        course = st.text_input(f"Rank #{i} Course Code & Name", key=f"course_{i}", placeholder=f"e.g., ECON {3000+i*10} - Course Title")
        ranked_courses.append(course.strip())

    st.markdown("---")

    st.subheader("4. Teaching Load & Schedule")
    st.write("**Desired course count per semester (ALPHA VERSION: Fall & Spring only):**")
    
    col_fall, col_spring = st.columns(2)
    with col_fall:
        fall_courses = st.number_input("Fall Semester Courses", min_value=0, max_value=5, value=2, step=1)
    with col_spring:
        spring_courses = st.number_input("Spring Semester Courses", min_value=0, max_value=5, value=2, step=1)

    course_overload = st.radio(
        "Would you like to include a course overload (e.g., 4th course) for extra compensation?",
        options=["No", "Yes", "Maybe / Open to discussion"]
    )

    st.markdown("---")

    st.subheader("5. Unique Circumstances & Special Requests")
    unique_circumstances = st.text_area(
        "Please specify any unique circumstances affecting your teaching load "
        "(e.g., joint teaching appointment, contractual course reduction, course buyout, or planned sabbatical leave):",
        placeholder="Enter details here or leave blank if not applicable..."
    )

    # Submit Button
    submitted = st.form_submit_button("Submit Preferences")

# -----------------------------------------------------------------------------
# 2. FORM SUBMISSION PROCESSING
# -----------------------------------------------------------------------------
if submitted:
    if not full_name.strip() or not email.strip():
        st.error("Please provide both your Full Name and Email address before submitting.")
    else:
        record = {
            "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Full Name": full_name.strip(),
            "Email": email.strip(),
            "Principles Preferences": "; ".join(principles_prefs) if principles_prefs else "None",
            "Rank 1 Course": ranked_courses[0],
            "Rank 2 Course": ranked_courses[1],
            "Rank 3 Course": ranked_courses[2],
            "Rank 4 Course": ranked_courses[3],
            "Rank 5 Course": ranked_courses[4],
            "Rank 6 Course": ranked_courses[5],
            "Fall Desired Courses": fall_courses,
            "Spring Desired Courses": spring_courses,
            "Course Overload Interest": course_overload,
            "Unique Circumstances": unique_circumstances.strip() if unique_circumstances.strip() else "None"
        }

        df_new = pd.DataFrame([record])
        if not os.path.exists(CSV_FILE):
            df_new.to_csv(CSV_FILE, index=False)
        else:
            df_new.to_csv(CSV_FILE, mode='a', header=False, index=False)

        st.success("✅ Your teaching preferences have been successfully recorded!")

# -----------------------------------------------------------------------------
# 3. DIRECT HARDCODED ADMIN VIEW
# -----------------------------------------------------------------------------
st.markdown("---")
with st.expander("🔒 Admin Portal (Restricted Access)"):
    entered_password = st.text_input("Enter Admin Password", type="password", key="admin_pwd_v2")
    
    if entered_password:
        if entered_password == ADMIN_PASSWORD:
            st.success("Access Granted")
            
            if os.path.exists(CSV_FILE):
                df_data = pd.read_csv(CSV_FILE)
                st.write(f"**Total Responses Recorded:** {len(df_data)}")
                st.dataframe(df_data)
                
                csv_bytes = df_data.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Dataset (.csv)",
                    data=csv_bytes,
                    file_name="teacher_preferences_export.csv",
                    mime="text/csv"
                )
                
                st.markdown("---")
                st.caption("⚠️ **Danger Zone:** Permanently delete all recorded submissions.")
                
                if st.button("🗑️ Clear All Data", type="primary"):
                    os.remove(CSV_FILE)
                    st.warning("All submission data has been permanently cleared!")
                    st.rerun()
            else:
                st.info("No submission data exists yet.")
        else:
            st.error("Incorrect password. Access denied.")