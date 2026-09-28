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
    If there are any questions regarding course titles, course codes, or the form, feel free to ask the AI Helper in the bottom right corner.
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
        "FTNTT faculty: Would you like to include a course overload (e.g., 4th course) for extra compensation?",
        options=["No", "Yes", "Maybe / Open to discussion"]
    )

    st.markdown("---")

    st.subheader("5. Unique Circumstances & Special Requests")
    unique_circumstances = st.text_area(
        "Please specify any unique circumstances to the department that should be considered when arranging your teaching schedule for the next two (2) academic years "
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
    "ECON 1292": "Economic History of the Middle East",
    "ECON 1711": "Economics of Sustainability",
    "ECON 1915": "Introductory Selected Topics in Macroeconomics",
    "ECON 1916": "Introductory Selected Topics in Microeconomics",
    "ECON 1990": "Elective",

    # 2000-Level Courses
    "ECON 2315": "Macroeconomic Theory",
    "ECON 2316": "Microeconomic Theory",
    "ECON 2350": "Statistics for Economists",
    "ECON 2560": "Applied Econometrics",
    "ECON 2990": "Elective",

    # 3000-Level Courses
    "ECON 3255": "Economics of Financial Market Structure",
    "ECON 3290": "History of the Global Economy",
    "ECON 3291": "Development Economics",
    "ECON 3404": "International Food Policy",
    "ECON 3405": "A Critique of Capitalism",
    "ECON 3410": "Labor Economics",
    "ECON 3412": "Women's Labor and the Economy",
    "ECON 3413": "Health Economics and Healthcare Policy",
    "ECON 3416": "Behavioral Economics",
    "ECON 3420": "Urban Economic Issues",
    "ECON 3423": "Environmental Economics",
    "ECON 3424": "Law and Economics",
    "ECON 3425": "Energy Economics",
    "ECON 3440": "Public Finance",
    "ECON 3442": "Money and Banking",
    "ECON 3460": "Managerial Economics",
    "ECON 3462": "Bubbles, Busts, and Bailouts: Market and Regulatory Failures in the Financial Crisis",
    "ECON 3470": "American Economic History",
    "ECON 3480": "Industrial Organization and Public Policy",
    "ECON 3481": "Economics of Sports",
    "ECON 3490": "Public Choice Economics",
    "ECON 3520": "History of Economic Thought",
    "ECON 3635": "International Economics",
    "ECON 3711": "Economics of Race",
    "ECON 3720": "Economics of Conflict and Peace",
    "ECON 3915": "Intermediate Selected Topics in Macroeconomics",
    "ECON 3916": "Intermediate Selected Topics in Microeconomics",
    "ECON 3990": "Elective",

    # 4000-Level Courses
    "ECON 4637": "Monetary and Fiscal Policy",
    "ECON 4640": "Financial Economics",
    "ECON 4642": "International Trade",
    "ECON 4644": "International Macroeconomics and Finance",
    "ECON 4653": "Mathematics for Economics",
    "ECON 4680": "Competition Policy and Regulation",
    "ECON 4681": "Information Economics and Game Theory",
    "ECON 4692": "Senior Economics Seminar",
    "ECON 4915": "Advanced Selected Topics in Macroeconomics",
    "ECON 4916": "Advanced Selected Topics in Microeconomics",
    "ECON 4965": "Undergraduate Teaching Experience",
    "ECON 4970": "Junior/Senior Honors Project 1",
    "ECON 4971": "Junior/Senior Honors Project 2",
    "ECON 4990": "Elective",
    "ECON 4991": "Research",
    "ECON 4992": "Directed Study",
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

        # 1. Full Course Catalog Intent
        all_trigger_words = [
            "all codes", "all course codes", "all courses", "show all",
            "list all", "every course", "everything", "catalog", "full list", "all"
        ]

        # 2. Contact & Email Intent
        contact_trigger_words = [
            "contact", "email", "support", "help desk", "reach out",
            "who to contact", "admin email", "contact info"
        ]

        # 3. Form Rules & Instructions Intent
        form_trigger_words = [
            "rank", "preference", "load", "section", "password",
            "admin", "deadline", "submit", "due"
        ]

        if any(trigger in query_lower for trigger in all_trigger_words):
            cat_1000 = [f"• **{code}**: {title}" for code, title in COURSE_DATABASE.items() if code.startswith("ECON 1")]
            cat_2000 = [f"• **{code}**: {title}" for code, title in COURSE_DATABASE.items() if code.startswith("ECON 2")]
            cat_3000 = [f"• **{code}**: {title}" for code, title in COURSE_DATABASE.items() if code.startswith("ECON 3")]
            cat_4000 = [f"• **{code}**: {title}" for code, title in COURSE_DATABASE.items() if code.startswith("ECON 4")]

            response_text = (
                "**Full Undergraduate Economics Course Catalog:**\n\n"
                "**1000-Level Courses**\n" + "\n".join(cat_1000) + "\n\n"
                "**2000-Level Courses**\n" + "\n".join(cat_2000) + "\n\n"
                "**3000-Level Courses**\n" + "\n".join(cat_3000) + "\n\n"
                "**4000-Level Courses**\n" + "\n".join(cat_4000)
            )

        elif any(trigger in query_lower for trigger in contact_trigger_words):
            response_text = (
                "**Contact & Support Information:**\n\n"
                "• **Email Field**: Enter your official Northeastern email in Section 1.\n"
                "• **Department Contact**: Contact the Economics Department Chair or Program Coordinator for course planning questions.\n"
                "• **Technical Support**: Contact Northeastern ITS if you experience submission bugs."
            )

        elif any(trigger in query_lower for trigger in form_trigger_words):
            if "password" in query_lower or "admin" in query_lower:
                response_text = "The Admin Portal requires administrator credentials to view and download submissions."
            elif "load" in query_lower or "section" in query_lower:
                response_text = "Select your anticipated total teaching load (number of sections) for Fall and Spring."
            elif "deadline" in query_lower or "due" in query_lower or "submit" in query_lower:
                response_text = "The form does not list a submission deadline. Please confirm the deadline with the Economics Department."
            else:
                response_text = "Rank your top course choices using Rank #1 through Rank #6."

        else:
            # 4. Stand-out Keyword & Synonym Map directly derived from your COURSE_DATABASE
            standout_topic_map = {
                # Specific topics in database
                "food": ["food", "policy"],
                "history": ["history", "historical", "thought"],
                "law": ["law", "legal", "regulation", "court"],
                "health": ["health", "healthcare", "medical"],
                "crime": ["crime", "criminal"],
                "race": ["race", "racial"],
                "sports": ["sports", "sport"],
                "money": ["money", "banking", "monetary", "financial", "finance"],
                "data": ["data", "analysis", "statistics", "econometrics"],
                "macro": ["macro", "macroeconomics", "macroeconomic"],
                "micro": ["micro", "microeconomics", "microeconomic"],
                "labor": ["labor", "women's labor", "employment"],
                "game": ["game", "game theory", "information"],
                "peace": ["peace", "conflict"],
                "sustainability": ["sustainability", "environmental", "energy"],
                "urban": ["urban", "city"],
                "math": ["mathematics", "math", "tools"],
                "thesis": ["thesis", "senior economics seminar", "honors project", "research", "directed study"],
                "internship": ["internship", "experiential"],
                "teaching": ["teaching", "undergraduate teaching experience"]
            }

            clean_query = query_lower.replace("?", "").replace(",", "").replace(".", "").replace("!", "")
            raw_words = clean_query.split()

            # Remove filler grammatical words only
            ignore_words = {
                "what", "is", "are", "the", "code", "for", "course", "courses", "class", "classes",
                "show", "me", "list", "of", "in", "a", "an", "and", "or", "to", "econ", "economics",
                "which", "find", "get", "do", "you", "have", "about", "on", "with", "tell"
            }
            search_tokens = [w for w in raw_words if w not in ignore_words and len(w) >= 2]

            scored_matches = []

            for code, title in COURSE_DATABASE.items():
                title_lower = title.lower()
                code_lower = code.lower()
                score = 0

                # A. Numeric level checks (e.g. '1000s', '3000')
                for token in raw_words:
                    if token in ["1000", "1000s", "1000-level"] and code.startswith("ECON 1"):
                        score += 10
                    elif token in ["2000", "2000s", "2000-level"] and code.startswith("ECON 2"):
                        score += 10
                    elif token in ["3000", "3000s", "3000-level"] and code.startswith("ECON 3"):
                        score += 10
                    elif token in ["4000", "4000s", "4000-level"] and code.startswith("ECON 4"):
                        score += 10

                # B. Direct word & partial token matches against code/title
                for token in search_tokens:
                    if token in code_lower:
                        score += 15
                    if token in title_lower:
                        score += 10

                # C. Topic Map Synonym Matches
                for topic, keywords in standout_topic_map.items():
                    if topic in clean_query or any(kw in clean_query for kw in keywords):
                        if any(kw in title_lower for kw in keywords):
                            score += 8

                if score > 0:
                    scored_matches.append((score, f"• **{code}**: {title}"))

            # Rank by relevance score
            scored_matches.sort(key=lambda x: x[0], reverse=True)
            matches = list(dict.fromkeys([item[1] for item in scored_matches]))

            if matches:
                response_text = "Matching courses:\n\n" + "\n".join(matches[:10])
            else:
                response_text = (
                    "No direct course match found for that query. "
                    "Type **'all'** to see every code, or search stand-out terms like **'food'**, **'history'**, **'law'**, **'crime'**, **'sports'**, **'money'**, or **'3000s'**."
                )

        st.session_state.chat_messages.append({"role": "assistant", "content": response_text})
        st.rerun()