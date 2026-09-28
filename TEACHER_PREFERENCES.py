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
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

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
        if not ADMIN_PASSWORD:
            st.error("Admin access is disabled. Set the ADMIN_PASSWORD environment variable.")
        elif entered_password == ADMIN_PASSWORD:
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

# ==========================================
# POPUP AI ASSISTANT (COURSE HELPER)
# ==========================================

# Reference data for Northeastern Economics courses
COURSE_DATABASE = {
    # 1000-Level Courses
    "ECON 1000": "Economics at Northeastern",
    "ECON 1113": "Data Analysis Tools for Economists",
    "ECON 1115": "Principles of Macroeconomics",
    "ECON 1116": "Principles of Microeconomics",
    "ECON 1125": "Recitation for ECON 1115",
    "ECON 1126": "Recitation for ECON 1116",
    "ECON 1230": "Healthcare and Medical Economics",
    "ECON 1240": "Economics of Crime",
    "ECON 1245": "Economics of Inequality",
    "ECON 1260": "Contested Issues in the U.S. Economy",
    "ECON 1290": "Topics in Economics",
    "ECON 1292": "Economic History of the Middle East",
    "ECON 1600": "The Global Economy",
    "ECON 1711": "Economics of Sustainability",
    "ECON 1990": "Elective",

    # 2000-Level Courses
    "ECON 2315": "Macroeconomic Theory",
    "ECON 2316": "Microeconomic Theory",
    "ECON 2350": "Statistics for Economists",
    "ECON 2560": "Applied Econometrics",
    "ECON 2990": "Elective",

    # 3000-Level Courses
    "ECON 3260": "Urban Economics",
    "ECON 3290": "Health Economics",
    "ECON 3410": "Labor Economics",
    "ECON 3420": "Industrial Organization",
    "ECON 3460": "Public Finance",
    "ECON 3470": "American Economic History",
    "ECON 3481": "Development Economics",
    "ECON 3490": "Economics of Sports",
    "ECON 3520": "History of Economic Thought",
    "ECON 3990": "Elective",

    # 4000-Level Courses
    "ECON 4635": "International Economics",
    "ECON 4640": "Financial Economics",
    "ECON 4650": "Behavioral Economics",
    "ECON 4653": "Mathematical Economics",
    "ECON 4680": "Environmental Economics",
    "ECON 4690": "Seminar in Economics",
    "ECON 4692": "Senior Economics Seminar",
    "ECON 4970": "Junior/Senior Honors Project 1",
    "ECON 4971": "Junior/Senior Honors Project 2",
    "ECON 4990": "Elective",
    "ECON 4991": "Research",
    "ECON 4992": "Directed Study",
    "ECON 4993": "Independent Study",
    "ECON 4994": "Internship",
    "ECON 4996": "Experiential Education Directed Study",
    "ECON 4997": "Senior Economics Thesis"
}

st.divider()

# 1. Custom CSS to float the popover button and style the overlay window
st.markdown(
    """
    <style>
    /* Fixed position in bottom right corner */
    div[data-testid="stPopover"] {
        position: fixed !important;
        bottom: 24px !important;
        right: 24px !important;
        width: auto !important;
        z-index: 999999 !important;
    }

    /* Convert button into a sleek circular icon button */
    div[data-testid="stPopover"] > button {
        width: 56px !important;
        height: 56px !important;
        min-width: 56px !important;
        border-radius: 50% !important;
        background-color: #5f6caf !important;
        color: white !important;
        border: none !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-size: 24px !important;
        box-shadow: 0px 4px 16px rgba(0, 0, 0, 0.35) !important;
        transition: transform 0.2s ease, background-color 0.2s ease !important;
    }

    /* Hide text inside the button if Streamlit forces popover label rendering */
    div[data-testid="stPopover"] > button p {
        font-size: 24px !important;
        margin: 0 !important;
    }

    div[data-testid="stPopover"] > button:hover {
        background-color: #4b5693 !important;
        transform: scale(1.1);
    }

    /* Pop-up chat window positioning and styling */
    div[data-testid="stPopoverBody"] {
        width: 360px !important;
        max-width: 90vw !important;
        border-radius: 16px !important;
        box-shadow: 0px 10px 30px rgba(0, 0, 0, 0.3) !important;
        border: 1px solid #333 !important;
        padding: 16px !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)
# 2. Floating Popover Widget
with st.popover("💬 AI Helper"):
    st.markdown("### 🤖 Course AI Assistant")
    st.caption("Search course codes, levels (e.g., 3000s), or ask form questions.")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": "Hello! Ask me about course codes or form instructions."}
        ]

    # Scrollable chat box container
    chat_container = st.container(height=320)
    with chat_container:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    if prompt := st.chat_input("Type a message..."):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})

        response_text = ""
        query_lower = prompt.lower().strip()

        # Check if the user is asking for all codes / full catalog
        all_trigger_words = ["all codes", "all course codes", "all courses", "show all", "list all", "every course", "everything"]
        if any(trigger in query_lower for trigger in all_trigger_words):
            # Format and group all courses by level
            cat_1000 = [f"• **{code}**: {title}" for code, title in COURSE_DATABASE.items() if code.startswith("ECON 1")]
            cat_2000 = [f"• **{code}**: {title}" for code, title in COURSE_DATABASE.items() if code.startswith("ECON 2")]
            cat_3000 = [f"• **{code}**: {title}" for code, title in COURSE_DATABASE.items() if code.startswith("ECON 3")]
            cat_4000 = [f"• **{code}**: {title}" for code, title in COURSE_DATABASE.items() if code.startswith("ECON 4")]

            response_text = (
                "**Here is the full list of undergraduate course codes:**\n\n"
                "**1000-Level Courses**\n" + "\n".join(cat_1000) + "\n\n"
                "**2000-Level Courses**\n" + "\n".join(cat_2000) + "\n\n"
                "**3000-Level Courses**\n" + "\n".join(cat_3000) + "\n\n"
                "**4000-Level Courses**\n" + "\n".join(cat_4000)
            )

        else:
            # Standard filtered/ranked keyword search
            ignore_words = {
                "what", "is", "are", "the", "code", "for", "course", "courses", "class", "classes",
                "show", "me", "list", "of", "in", "a", "an", "and", "or", "to", "econ", "economics"
            }

            raw_words = query_lower.replace("?", "").replace(",", "").split()
            keywords = [w for w in raw_words if w not in ignore_words and len(w) > 2]

            scored_matches = []
            for code, title in COURSE_DATABASE.items():
                combined_text = f"{code} {title}".lower()
                score = 0

                for w in raw_words:
                    if w in ["1000", "1000s", "level 1"] and code.startswith("ECON 1"):
                        score += 2
                    elif w in ["2000", "2000s", "level 2"] and code.startswith("ECON 2"):
                        score += 2
                    elif w in ["3000", "3000s", "level 3"] and code.startswith("ECON 3"):
                        score += 2
                    elif w in ["4000", "4000s", "level 4"] and code.startswith("ECON 4"):
                        score += 2

                for kw in keywords:
                    if kw in title.lower():
                        score += 3
                    elif kw in code.lower():
                        score += 3

                if score > 0:
                    scored_matches.append((score, f"**{code}**: {title}"))

            scored_matches.sort(key=lambda x: x[0], reverse=True)
            matches = list(dict.fromkeys([item[1] for item in scored_matches]))

            if matches:
                response_text = "Matching courses:\n\n" + "\n".join(f"- {m}" for m in matches[:8])
            elif "password" in query_lower or "admin" in query_lower:
                response_text = "The Admin Portal requires administrator credentials to view all submitted preferences."
            elif "rank" in query_lower or "preference" in query_lower:
                response_text = "Select your top course preferences using Rank 1 through Rank 6 in the main form."
            elif "load" in query_lower or "section" in query_lower:
                response_text = "Select your total teaching load (course sections) for Fall and Spring."
            else:
                response_text = "No direct course match found. You can ask for 'all codes' to view the entire course list, or search topics like 'macro' or '3000s'."

        st.session_state.chat_messages.append({"role": "assistant", "content": response_text})
        st.rerun()