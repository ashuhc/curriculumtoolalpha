import os
import json
import pandas as pd
import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="Faculty Teaching Preferences Form",
    page_icon="📋",
    layout="centered"
)

# Hardcoded Path & Configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, "teacher_preferences.csv")

COLUMNS = [
    "Timestamp", "Full Name", "Email", "Principles Preferences",
    "Rank 1 Course", "Rank 2 Course", "Rank 3 Course", "Rank 4 Course",
    "Rank 5 Course", "Rank 6 Course", "Fall Desired Courses",
    "Spring Desired Courses", "Course Overload Interest", "Unique Circumstances"
]

# List of unique faculty members extracted from enrollment records
DEFAULT_FACULTY_NAMES = [
    "Select your name...",
    "Adams, Brookelyn",
    "Alam, Mohammad",
    "Bakkal, Ilter",
    "Caicedo, Santiago",
    "Cao, Jianfei",
    "Cheng, Peiran",
    "Chowdhury, Pabitra",
    "Dana, James",
    "Dew, James",
    "Diaz Vargas, Dayanara",
    "Dupree, Jill",
    "Ellul, Christian",
    "Garofalo, Pablo",
    "Georges, Francis",
    "Gernhardt, Roy",
    "Gulbiten, Onsel",
    "Han, Yuling",
    "Hooker, Mark",
    "Jakubowski, Aleksandra",
    "Jung, Jae Wook",
    "Khanna, Shantanu",
    "Konan, Martin",
    "Kwoka, John",
    "Marks, Mindy",
    "Mohammed, Abdul Raheem Shariq",
    "Mughal, Abdul",
    "Pacheco, Paul Nicholas",
    "Peng, Shenghao",
    "Piao, Richeng",
    "Porter, Gerald",
    "Prakash, Nishith",
    "Prina, Silvia",
    "Richardson, Samuel",
    "Roble, Benjamin",
    "Ross, Matthew",
    "Shabanpour, MuhammadHussian",
    "Shahidinejad, Andres",
    "Shi, Xiaolin",
    "Silva, Mario Rafael",
    "Stone, Michael",
    "Tao, Tianyi",
    "Tardiff, Timothy",
    "Thompson, Jacob",
    "Toone, Kalten",
    "Triest, Robert",
    "Ulusoy, Veysel",
    "Unal, Cankutcem",
    "Venkatesan, Madhavi",
    "Vicentini, Gustavo",
    "Wolfe, Sarah",
    "Zhang, Shuo",
    "Zhou, Nan"
]

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
    "ECON 4997": "Senior Economics Thesis",
}

# Reference data for Northeastern Economics course descriptions (for AI Assistant)
COURSE_DESCRIPTIONS = {
    # 1000-Level Courses
    "ECON 1000": {
        "title": "Economics at Northeastern",
        "description": "Introduces first-year economics majors to the academic and professional landscape of economics at Northeastern, including co-op opportunities and career paths."
    },
    "ECON 1113": {
        "title": "Data Analysis Tools for Economists",
        "description": "Introduces basic statistical and computational tools used in economic analysis, data manipulation, visualization, and basic regression techniques."
    },
    "ECON 1115": {
        "title": "Principles of Macroeconomics",
        "description": "Examines the economy as a whole, including national income, inflation, unemployment, fiscal and monetary policy, economic growth, and international trade."
    },
    "ECON 1116": {
        "title": "Principles of Microeconomics",
        "description": "Analyzes behavior of individual consumers and firms, market structures, price determination, resource allocation, and government intervention in markets."
    },
    "ECON 1125": {
        "title": "Recitation for ECON 1115",
        "description": "Provides small-group discussion, problem-solving, and practical application of concepts covered in Principles of Macroeconomics."
    },
    "ECON 1126": {
        "title": "Recitation for ECON 1116",
        "description": "Provides small-group discussion, problem-solving, and practical application of concepts covered in Principles of Microeconomics."
    },
    "ECON 1230": {
        "title": "Healthcare and Medical Economics",
        "description": "Explores the economics of healthcare delivery, insurance markets, medical technology, health outcomes, and government health policy."
    },
    "ECON 1240": {
        "title": "Economics of Crime",
        "description": "Applies economic principles to criminal behavior, law enforcement, deterrence, sentencing policy, drug regulation, and the economic costs of crime."
    },
    "ECON 1245": {
        "title": "Economics of Inequality",
        "description": "Investigates the distribution of income and wealth, sources of economic inequality, mobility, poverty, discrimination, and redistribution policies."
    },
    "ECON 1260": {
        "title": "Contested Issues in the U.S. Economy",
        "description": "Examines contemporary debates in American economic policy, including tax policy, minimum wage, climate change, trade, and financial regulation."
    },
    "ECON 1292": {
        "title": "Economic History of the Middle East",
        "description": "Surveys the long-run economic development, institutional evolution, trade routes, resource allocation, and modern economic challenges of the Middle East."
    },
    "ECON 1711": {
        "title": "Economics of Sustainability",
        "description": "Analyzes the economic dimensions of environmental sustainability, natural resource management, ecological footprints, and green growth strategies."
    },
    "ECON 1915": {
        "title": "Introductory Selected Topics in Macroeconomics",
        "description": "Covers special introductory topics in macroeconomic theory, policy, or empirical research."
    },
    "ECON 1916": {
        "title": "Introductory Selected Topics in Microeconomics",
        "description": "Covers special introductory topics in microeconomic analysis, decision-making, or market applications."
    },
    "ECON 1990": {
        "title": "Elective",
        "description": "Transfer or elective credit in economics at the 1000-level."
    },

    # 2000-Level Courses
    "ECON 2315": {
        "title": "Macroeconomic Theory",
        "description": "Provides an intermediate analysis of aggregate demand, aggregate supply, economic growth theories, business cycle models, and macroeconomic policy."
    },
    "ECON 2316": {
        "title": "Microeconomic Theory",
        "description": "Provides an intermediate analysis of consumer choice theory, firm production, general equilibrium, market power, game theory, and welfare economics."
    },
    "ECON 2350": {
        "title": "Statistics for Economists",
        "description": "Covers probability theory, descriptive statistics, sampling distributions, hypothesis testing, and simple linear regression applied to economic data."
    },
    "ECON 2560": {
        "title": "Applied Econometrics",
        "description": "Focuses on quantitative empirical methods in economics, multiple linear regression, model specification, diagnostic testing, and econometric software applications."
    },
    "ECON 2990": {
        "title": "Elective",
        "description": "Transfer or elective credit in economics at the 2000-level."
    },

    # 3000-Level Courses
    "ECON 3255": {
        "title": "Economics of Financial Market Structure",
        "description": "Examines the structure, regulation, liquidity, and trading mechanisms of modern financial markets, exchanges, and institutional investors."
    },
    "ECON 3290": {
        "title": "History of the Global Economy",
        "description": "Traces the evolution of global trade, industrialization, financial systems, global economic integration, and international crises from historical perspectives."
    },
    "ECON 3291": {
        "title": "Development Economics",
        "description": "Studies economic growth, poverty alleviation, human capital development, institutional quality, and trade strategies in low- and middle-income nations."
    },
    "ECON 3404": {
        "title": "International Food Policy",
        "description": "Analyzes global food security, agricultural trade policy, food distribution, agricultural subsidies, and sustainable farming economics."
    },
    "ECON 3405": {
        "title": "A Critique of Capitalism",
        "description": "Explores heterodox economic perspectives, historical critiques of market economies, Marxian economics, and alternative economic systems."
    },
    "ECON 3410": {
        "title": "Labor Economics",
        "description": "Analyzes labor supply and demand, wage differentials, human capital investment, labor unions, employment legislation, and unemployment."
    },
    "ECON 3412": {
        "title": "Women's Labor and the Economy",
        "description": "Investigates gender dynamics in the workforce, the gender wage gap, occupational segregation, unpaid care labor, and family policy economics."
    },
    "ECON 3413": {
        "title": "Health Economics and Healthcare Policy",
        "description": "Applies microeconomic theory to health insurance, hospital competition, pharmaceutical economics, physician incentive structures, and reform policy."
    },
    "ECON 3416": {
        "title": "Behavioral Economics",
        "description": "Integrates psychology and economics to study decision-making biases, bounded rationality, heuristics, prospect theory, and behavioral policy interventions."
    },
    "ECON 3420": {
        "title": "Urban Economic Issues",
        "description": "Examines spatial economics, housing markets, urban transportation, local public finance, gentrification, urban poverty, and municipal policies."
    },
    "ECON 3423": {
        "title": "Environmental Economics",
        "description": "Studies environmental externalities, pollution control policies, carbon pricing, ecosystem valuation, and international climate agreements."
    },
    "ECON 3424": {
        "title": "Law and Economics",
        "description": "Applies economic analysis to legal principles, focusing on property rights, contract law, tort liability, law enforcement, and judicial incentive structures."
    },
    "ECON 3425": {
        "title": "Energy Economics",
        "description": "Examines energy supply and demand, fossil fuels, renewable energy, market imperfections, greenhouse gas emissions, and energy security policies."
    },
    "ECON 3440": {
        "title": "Public Finance",
        "description": "Examines government expenditure, taxation principles, public goods provision, social insurance programs, fiscal policy, and tax incidence."
    },
    "ECON 3442": {
        "title": "Money and Banking",
        "description": "Studies monetary systems, commercial banking, central bank operations, financial intermediation, interest rates, and monetary policy implementation."
    },
    "ECON 3460": {
        "title": "Managerial Economics",
        "description": "Applies microeconomic principles to managerial decision-making, pricing strategies, market demand analysis, production efficiency, and competitive strategy."
    },
    "ECON 3462": {
        "title": "Bubbles, Busts, and Bailouts: Market and Regulatory Failures in the Financial Crisis",
        "description": "Investigates the mechanics of financial panics, asset price bubbles, systemic risk, bank runs, regulatory responses, and historical financial crises."
    },
    "ECON 3470": {
        "title": "American Economic History",
        "description": "Examines the long-run economic growth of the United States, covering colonial development, slavery, industrialization, the Great Depression, and postwar expansion."
    },
    "ECON 3480": {
        "title": "Industrial Organization and Public Policy",
        "description": "Analyzes firm conduct in imperfectly competitive markets, oligopoly behavior, antitrust law, merger policy, cartels, and industry regulation."
    },
    "ECON 3481": {
        "title": "Economics of Sports",
        "description": "Applies economic analysis to professional and college sports, examining sports as an economic activity and evaluating empirical evidence on key industry questions."
    },
    "ECON 3490": {
        "title": "Public Choice Economics",
        "description": "Applies economic theory to political science processes, studying voting mechanisms, interest groups, bureaucracy, political rent-seeking, and constitutional economics."
    },
    "ECON 3520": {
        "title": "History of Economic Thought",
        "description": "Surveys the evolution of economic ideas from Classical economists (Smith, Ricardo, Mill) through Marx, Keynes, and modern neoclassical syntheses."
    },
    "ECON 3635": {
        "title": "International Economics",
        "description": "Analyzes international trade patterns, tariffs, trade agreements, balance of payments, foreign exchange markets, and global economic integration."
    },
    "ECON 3711": {
        "title": "Economics of Race",
        "description": "Applies economic tools to study racial disparities in income, housing, employment, criminal justice, education, wealth accumulation, and civil rights policies."
    },
    "ECON 3720": {
        "title": "Economics of Conflict and Peace",
        "description": "Investigates the economic causes and consequences of armed conflict, terrorism, defense spending, post-conflict reconstruction, and peacebuilding."
    },
    "ECON 3915": {
        "title": "Intermediate Selected Topics in Macroeconomics",
        "description": "Explores specialized intermediate topics in macroeconomic theory and policy."
    },
    "ECON 3916": {
        "title": "Intermediate Selected Topics in Microeconomics",
        "description": "Explores specialized intermediate topics in microeconomic theory and policy."
    },
    "ECON 3990": {
        "title": "Elective",
        "description": "Transfer or elective credit in economics at the 3000-level."
    },

    # 4000-Level Courses
    "ECON 4637": {
        "title": "Monetary and Fiscal Policy",
        "description": "Provides an advanced evaluation of central bank interest rate policy, quantitative easing, national debt dynamics, inflation targeting, and macroeconomic policy coordination."
    },
    "ECON 4640": {
        "title": "Financial Economics",
        "description": "Provides rigorous analysis of asset pricing models, portfolio selection theory, efficient market hypothesis, risk management, and derivative pricing."
    },
    "ECON 4642": {
        "title": "International Trade",
        "description": "Advanced theoretical examination of trade models (Ricardian, Heckscher-Ohlin, Melitz), trade policy, tariffs, quotas, and global supply chains."
    },
    "ECON 4644": {
        "title": "International Macroeconomics and Finance",
        "description": "Analyzes open-economy macroeconomics, exchange rate determination models, global capital flows, financial contagions, and sovereign debt."
    },
    "ECON 4653": {
        "title": "Mathematics for Economics",
        "description": "Develops mathematical techniques essential for advanced economic theory, including multivariate calculus, linear algebra, constrained optimization, and differential equations."
    },
    "ECON 4680": {
        "title": "Competition Policy and Regulation",
        "description": "Advanced analysis of antitrust economics, regulatory frameworks for natural monopolies, anti-competitive practices, and merger enforcement."
    },
    "ECON 4681": {
        "title": "Information Economics and Game Theory",
        "description": "Examines strategic decision-making under uncertainty, Nash equilibria, asymmetric information, signaling models, moral hazard, adverse selection, and mechanism design."
    },
    "ECON 4692": {
        "title": "Senior Economics Seminar",
        "description": "Cap-stone seminar requiring original economic research, data analysis, literature review, and formal paper presentation."
    },
    "ECON 4915": {
        "title": "Advanced Selected Topics in Macroeconomics",
        "description": "Provides advanced instruction on cutting-edge research topics in macroeconomics."
    },
    "ECON 4916": {
        "title": "Advanced Selected Topics in Microeconomics",
        "description": "Provides advanced instruction on cutting-edge research topics in microeconomics."
    },
    "ECON 4965": {
        "title": "Undergraduate Teaching Experience",
        "description": "Provides upper-level undergraduate students with supervised teaching assistant experience in core economics courses."
    },
    "ECON 4970": {
        "title": "Junior/Senior Honors Project 1",
        "description": "First semester of advanced independent honors research under faculty supervision."
    },
    "ECON 4971": {
        "title": "Junior/Senior Honors Project 2",
        "description": "Second semester completion and defense of undergraduate honors thesis."
    },
    "ECON 4990": {
        "title": "Elective",
        "description": "Transfer or elective credit in economics at the 4000-level."
    },
    "ECON 4991": {
        "title": "Research",
        "description": "Offers structured independent research experience under the direction of an economics faculty member."
    },
    "ECON 4992": {
        "title": "Directed Study",
        "description": "Offers individual, specialized study under the direction of a faculty member on an approved economics topic."
    },
    "ECON 4994": {
        "title": "Internship",
        "description": "Provides students with practical economic experience through approved professional employment opportunities."
    },
    "ECON 4996": {
        "title": "Experiential Education Directed Study",
        "description": "Combines academic major coursework with student's approved practical experiential education. Restricted to those students who are using the course to fulfill their experiential education requirement."
    },
    "ECON 4997": {
        "title": "Senior Economics Thesis",
        "description": "Substantial individual research thesis completed under faculty advisor supervision."
    }
}

FACULTY_FILE = "custom_faculty.json"
COURSES_FILE = "custom_courses.json"


def load_faculty():
    if os.path.exists(FACULTY_FILE):
        try:
            with open(FACULTY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    
    # First-time run: write default list to file and return it
    save_faculty(DEFAULT_FACULTY_NAMES)
    return list(DEFAULT_FACULTY_NAMES)

def save_faculty(faculty_list):
    with open(FACULTY_FILE, "w") as f:
        json.dump(faculty_list, f, indent=4)

def load_courses():
    if os.path.exists(COURSES_FILE):
        with open(COURSES_FILE, "r") as f:
            return json.load(f)
    return dict(COURSE_DATABASE)  # Fallback to default dict

def save_courses(course_dict):
    with open(COURSES_FILE, "w") as f:
        json.dump(course_dict, f, indent=4)

if "faculty_names" not in st.session_state:
    st.session_state.faculty_names = load_faculty()

if "course_database" not in st.session_state:
    st.session_state.course_database = load_courses()

# --- INITIALIZE LIVE & STAGING STATES ---
if "faculty_names" not in st.session_state:
    st.session_state.faculty_names = load_faculty()

# Draft state for uncommitted faculty changes
if "draft_faculty" not in st.session_state:
    st.session_state.draft_faculty = list(st.session_state.faculty_names)

if "course_database" not in st.session_state:
    st.session_state.course_database = load_courses()

# Draft state for uncommitted course changes
if "draft_courses" not in st.session_state:
    st.session_state.draft_courses = dict(st.session_state.course_database)

def format_course_label(code, data):
    """Formats course for dropdown UI cleanly as 'CODE - Title'."""
    if isinstance(data, dict):
        title = data.get("title", "")
    else:
        title = str(data)
    return f"{code} - {title}" if title else code

# Build clean options list for Streamlit selectboxes
COURSE_OPTIONS = ["Select a course..."] + [
    format_course_label(code, data) 
    for code, data in st.session_state.course_database.items()
]

# Ensure CSV file exists with columns at startup
if not os.path.exists(CSV_FILE):
    pd.DataFrame(columns=COLUMNS).to_csv(CSV_FILE, index=False)

# Sync Session State with CSV
if "df_responses" not in st.session_state:
    st.session_state.df_responses = pd.read_csv(CSV_FILE)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "econpassword123")

# Header Section
st.title("📋 Faculty Teaching Preferences Form")
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
        full_name = st.selectbox("Full Name*", options=st.session_state.faculty_names)
    with col2:
        email = st.text_input("Email*", placeholder="Preferred contact email")

    st.markdown("---")

    st.subheader("2. Principles Course Preferences")

    # Target specific Principles courses: Statistics (1113), Macroecon (1115), Microecon (1116)
    PRINCIPLES_CODES = ("ECON 2350", "ECON 1115", "ECON 1116")

    principles_options = [c for c in COURSE_OPTIONS if c.startswith(PRINCIPLES_CODES)] + ["None / Not Applicable"]

    principles_prefs = st.multiselect(
        "Which Principles courses would you prefer to teach? (Select all that apply)",
        options=principles_options
    )

    st.markdown("---")

    st.subheader("3. Top 6 Undergraduate Course Preferences")
    st.write("Rank your top 6 course choices from the dropdown menus below.")

    # Dropdowns automatically reflect dynamic additions/deletions from st.session_state
    rank_1 = st.selectbox("Rank #1 Course Code & Name", options=COURSE_OPTIONS, index=0, key="rank_1")
    rank_2 = st.selectbox("Rank #2 Course Code & Name", options=COURSE_OPTIONS, index=0, key="rank_2")
    rank_3 = st.selectbox("Rank #3 Course Code & Name", options=COURSE_OPTIONS, index=0, key="rank_3")
    rank_4 = st.selectbox("Rank #4 Course Code & Name", options=COURSE_OPTIONS, index=0, key="rank_4")
    rank_5 = st.selectbox("Rank #5 Course Code & Name", options=COURSE_OPTIONS, index=0, key="rank_5")
    rank_6 = st.selectbox("Rank #6 Course Code & Name", options=COURSE_OPTIONS, index=0, key="rank_6")

    # Store selected values in a list for submission processing
    ranked_courses = [
        rank_1 if rank_1 != "Select a course..." else "None",
        rank_2 if rank_2 != "Select a course..." else "None",
        rank_3 if rank_3 != "Select a course..." else "None",
        rank_4 if rank_4 != "Select a course..." else "None",
        rank_5 if rank_5 != "Select a course..." else "None",
        rank_6 if rank_6 != "Select a course..." else "None"
    ]

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
    if full_name == "Select your name..." or not email.strip():
        st.error("Please select your FULL NAME and enter your EMAIL ADDRESS before submitting.")
    else:
        record = {
            "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Full Name": full_name,
            "Email": email.strip(),
            "Principles Preferences": "; ".join(principles_prefs) if principles_prefs else "None",
            "Rank 1 Course": rank_1 if rank_1 != "Select a course..." else "None",
            "Rank 2 Course": rank_2 if rank_2 != "Select a course..." else "None",
            "Rank 3 Course": rank_3 if rank_3 != "Select a course..." else "None",
            "Rank 4 Course": rank_4 if rank_4 != "Select a course..." else "None",
            "Rank 5 Course": rank_5 if rank_5 != "Select a course..." else "None",
            "Rank 6 Course": rank_6 if rank_6 != "Select a course..." else "None",
            "Fall Desired Courses": fall_courses,
            "Spring Desired Courses": spring_courses,
            "Course Overload Interest": course_overload,
            "Unique Circumstances": unique_circumstances.strip() if unique_circumstances.strip() else "None"
        }

        df_new = pd.DataFrame([record])

        # 1. Load existing disk data if present to prevent overwriting
        if os.path.exists(CSV_FILE):
            existing_df = pd.read_csv(CSV_FILE)
            updated_df = pd.concat([existing_df, df_new], ignore_index=True)
        else:
            updated_df = df_new

        # 2. Save updated DataFrame to disk
        updated_df.to_csv(CSV_FILE, index=False)

        # 3. Update Streamlit session state
        st.session_state.df_responses = updated_df

        # 4. Set success flag so message persists across rerun
        st.session_state["submitted_success"] = True
        st.rerun()

# Display success message at top of page or above form if flag is set
if st.session_state.get("submitted_success"):
    st.success("✅ Your teaching preferences have been successfully recorded!")
    # Clear flag so message goes away on subsequent interactions
    del st.session_state["submitted_success"]

# -----------------------------------------------------------------------------
# 3. DIRECT HARDCODED ADMIN VIEW
# -----------------------------------------------------------------------------
st.markdown("---")
with st.expander("🔒 Admin Portal (Restricted Access)"):
    # Initialize admin authentication in session state if not already set
    if "admin_authenticated" not in st.session_state:
        st.session_state["admin_authenticated"] = False

    # If NOT logged in, show the login form
    if not st.session_state["admin_authenticated"]:
        with st.form("admin_login_form"):
            entered_password = st.text_input("Enter Admin Password", type="password")
            submit_button = st.form_submit_button("Login")

        if submit_button:
            if entered_password == ADMIN_PASSWORD:
                st.session_state["admin_authenticated"] = True
                st.rerun()  # Refresh immediately to show the unlocked portal
            else:
                st.error("Incorrect password. Access denied.")

    # If authenticated, show the admin portal content
    else:
        st.success("Access Granted")
        
        # Optional Logout Button
        if st.button("🔒 Logout"):
            st.session_state["admin_authenticated"] = False
            st.rerun()

        admin_tab1, admin_tab2, admin_tab3 = st.tabs([
            "📊 View Submissions", 
            "👨‍🏫 Manage Faculty Names", 
            "📚 Manage Course Catalog"
        ])

        with admin_tab1:
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

                if st.button("💾 Sync All Memory to CSV"):
                    st.session_state.df_responses.to_csv(CSV_FILE, index=False)
                    st.success(f"Successfully wrote {len(st.session_state.df_responses)} records to {CSV_FILE}!")
        with admin_tab2:
            st.markdown("### Manage Faculty Dropdown List (Staging)")
            
            # 0. Check for success notification banner surviving st.rerun()
            if "faculty_commit_success" in st.session_state:
                st.success(st.session_state.faculty_commit_success)
                del st.session_state.faculty_commit_success  # Display once then clear

            # Check for uncommitted staging changes
            has_faculty_changes = st.session_state.draft_faculty != st.session_state.faculty_names
            if has_faculty_changes:
                st.warning("⚠️ You have uncommitted changes in your faculty staging buffer.")
            
            col_add, col_remove = st.columns(2)
            
            # --- 1. STAGE ADDITION ---
            with col_add:
                st.markdown("#### Stage Add Faculty")
                with st.form("stage_add_faculty_form"):
                    new_fac = st.text_input("New Faculty Name (e.g., 'Smith, Jane')")
                    if st.form_submit_button("Stage Addition"):
                        cleaned = new_fac.strip()
                        if cleaned and cleaned not in st.session_state.draft_faculty:
                            st.session_state.draft_faculty.append(cleaned)
                            
                            # Sort draft list alphabetically (keeping default prompt at top)
                            has_select = "Select your name..." in st.session_state.draft_faculty
                            names_only = [f for f in st.session_state.draft_faculty if f != "Select your name..."]
                            names_only.sort()
                            st.session_state.draft_faculty = (
                                ["Select your name..."] + names_only if has_select else names_only
                            )
                            
                            st.toast(f"✅ Staged '{cleaned}' for addition", icon="🎉")
                            st.rerun()
                        elif cleaned in st.session_state.draft_faculty:
                            st.warning(f"'{cleaned}' is already in draft state.")

            # --- 2. STAGE REMOVAL ---
            with col_remove:
                st.markdown("#### Stage Remove Faculty")
                names_only = [f for f in st.session_state.draft_faculty if f != "Select your name..."]
                fac_remove_options = ["Select faculty to remove..."] + names_only
                
                if names_only:
                    fac_to_stage_remove = st.selectbox(
                        "Select Faculty to Remove", 
                        options=fac_remove_options, 
                        key="stage_fac_rem"
                    )
                    
                    if st.button("Stage Removal", type="secondary"):
                        if fac_to_stage_remove != "Select faculty to remove...":
                            st.session_state.draft_faculty = [
                                f for f in st.session_state.draft_faculty if f != fac_to_stage_remove
                            ]
                            st.toast(f"🗑️ Staged removal of '{fac_to_stage_remove}'", icon="ℹ️")
                            st.rerun()
                        else:
                            st.warning("Please select a valid faculty member to remove.")
                else:
                    st.caption("No remaining faculty to remove in draft.")

            st.divider()

            # --- 3. PREVIEW & COMMIT CONTROLS ---
            st.markdown("#### Preview & Commit Changes")
            st.caption(f"Draft catalog contains {len(st.session_state.draft_faculty)} entries.")
            
            btn_col1, btn_col2 = st.columns([1, 1])
            with btn_col1:
                if st.button("🚀 Commit & Publish Faculty Changes", type="primary", disabled=not has_faculty_changes):
                    # Apply draft changes to live state
                    st.session_state.faculty_names = list(st.session_state.draft_faculty)
                    # Write to disk
                    save_faculty(st.session_state.faculty_names)
                    
                    # Store banner message in session state so it displays after st.rerun()
                    st.session_state.faculty_commit_success = "✅ Faculty list changes successfully committed and published to live app!"
                    st.toast("Faculty list updated successfully!", icon="🚀")
                    st.rerun()

            with btn_col2:
                if st.button("🔄 Discard Draft Changes", disabled=not has_faculty_changes):
                    st.session_state.draft_faculty = list(st.session_state.faculty_names)
                    st.session_state.faculty_commit_success = "ℹ️ Discarded uncommitted faculty changes."
                    st.rerun()

        with admin_tab3:
            st.markdown("### Manage Course Catalog Dropdown List (Staging)")
            
            # Display success banner surviving st.rerun()
            if "course_commit_success" in st.session_state:
                st.success(st.session_state.course_commit_success)
                del st.session_state.course_commit_success

            # Check for uncommitted staging changes
            has_course_changes = st.session_state.draft_courses != st.session_state.course_database
            if has_course_changes:
                st.warning("⚠️ You have uncommitted changes in your course staging buffer.")

            col_c_add, col_c_rem = st.columns(2)

            # --- 1. STAGE COURSE ADDITION ---
            with col_c_add:
                st.markdown("#### Stage Add Course")
                with st.form("stage_add_course_form"):
                    c_code = st.text_input("Course Code (e.g., 'ECON 1260')")
                    c_title = st.text_input("Course Title (e.g., 'Contested Issues in the U.S. Economy')")
                    c_desc = st.text_area("Course Description", help="Add the detailed course description here.")
                    
                    if st.form_submit_button("Stage Course"):
                        if c_code and c_title:
                            code_clean = c_code.strip().upper()
                            # Saves Code as key, with Title AND Description in the dict object
                            st.session_state.draft_courses[code_clean] = {
                                "title": c_title.strip(),
                                "description": c_desc.strip() if c_desc else ""
                            }
                            
                            st.toast(f"✅ Staged {code_clean}", icon="📚")
                            st.rerun()
                        else:
                            st.warning("Course Code and Course Title are required.")

            # --- 2. STAGE COURSE REMOVAL ---
            with col_c_rem:
                st.markdown("#### Stage Remove Course")
                if st.session_state.draft_courses:
                    # Build dropdown showing ONLY "Code - Title" (keeping description hidden from menu)
                    course_remove_options = ["Select course to remove..."]
                    for code, data in st.session_state.draft_courses.items():
                        title = data.get("title", str(data)) if isinstance(data, dict) else str(data)
                        course_remove_options.append(f"{code} - {title}")
                    
                    selected_course_str = st.selectbox(
                        "Select Course to Remove", 
                        options=course_remove_options, 
                        key="stage_course_rem"
                    )
                    
                    if st.button("Stage Removal", key="btn_stage_c_rem"):
                        if selected_course_str != "Select course to remove...":
                            # Extract course code before the " - "
                            code_to_remove = selected_course_str.split(" - ")[0]
                            
                            # Deletes the entire object (code, title, and description)
                            if code_to_remove in st.session_state.draft_courses:
                                del st.session_state.draft_courses[code_to_remove]
                                st.toast(f"🗑️ Staged removal of {code_to_remove}", icon="ℹ️")
                                st.rerun()
                        else:
                            st.warning("Please select a valid course to remove.")
                else:
                    st.caption("No courses available to remove in draft.")

            st.divider()

            # --- 3. PREVIEW & COMMIT CONTROLS ---
            st.markdown("#### Preview & Commit Course Changes")
            st.caption(f"Draft catalog contains {len(st.session_state.draft_courses)} entries.")
            
            btn_cc1, btn_cc2 = st.columns([1, 1])
            
            with btn_cc1:
                if st.button("🚀 Commit & Publish Course Catalog", type="primary", disabled=not has_course_changes):
                    # Write draft mapping directly to live session and persistent JSON disk file
                    st.session_state.course_database = dict(st.session_state.draft_courses)
                    save_courses(st.session_state.course_database)
                    
                    st.session_state.course_commit_success = "✅ Course catalog changes successfully committed and published to live app!"
                    st.toast("Course catalog updated successfully!", icon="🚀")
                    st.rerun()

            with btn_cc2:
                if st.button("🔄 Discard Course Draft", disabled=not has_course_changes):
                    st.session_state.draft_courses = dict(st.session_state.course_database)
                    st.session_state.course_commit_success = "ℹ️ Discarded uncommitted course catalog changes."
                    st.rerun()

        # --------------------------------------------------
        # Original Data Sync & Danger Zone Actions
        # --------------------------------------------------
        st.divider()

        st.caption("⚠️ **Danger Zone:** Permanently delete all recorded preference submissions.")

        if st.button("🗑️ Clear All Data", type="primary"):
            st.session_state.df_responses = pd.DataFrame(columns=COLUMNS)
            st.session_state.df_responses.to_csv(CSV_FILE, index=False)
            st.success("✅ All submission data has been permanently cleared!")
            st.rerun()

# ==========================================
# POPUP AI ASSISTANT (COURSE HELPER)
# ==========================================

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
                response_text = "Submit preferences before the departmental deadline listed at the top of the form."
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

            for code, info in st.session_state.course_database.items():
                # Extract title and description regardless of database schema
                if isinstance(info, dict):
                    title = info.get("title", "")
                    desc = info.get("description", "")
                else:
                    title = str(info)
                    # Fallback to COURSE_DESCRIPTIONS if separate dict exists
                    desc_dict = globals().get("COURSE_DESCRIPTIONS", {}).get(code, {})
                    desc = desc_dict.get("description", "") if isinstance(desc_dict, dict) else ""

                title_lower = title.lower()
                desc_lower = desc.lower()
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

                # B. Direct word & partial token matches against code, title, and description
                for token in search_tokens:
                    if token in code_lower:
                        score += 15
                    if token in title_lower:
                        score += 10
                    if desc_lower and token in desc_lower:
                        score += 5

                # C. Topic Map Synonym Matches
                for topic, keywords in standout_topic_map.items():
                    if topic in clean_query or any(kw in clean_query for kw in keywords):
                        if any(kw in title_lower or kw in desc_lower for kw in keywords):
                            score += 8

                if score > 0:
                    if desc:
                        match_str = f"* **{code}**: {title}\n  _{desc}_"
                    else:
                        match_str = f"* **{code}**: {title}"

                    scored_matches.append((score, match_str))

            # Rank by relevance score
            scored_matches.sort(key=lambda x: x[0], reverse=True)
            matches = list(dict.fromkeys([item[1] for item in scored_matches]))

                # Ensure response_text exists before appending
            if matches:
                # Separate matched courses with double newlines so descriptions read cleanly
                response_text = "Matching courses:\n\n" + "\n\n".join(matches[:5])
            else:
                response_text = (
                    "No direct course match found for that query. "
                    "Type **'all'** to see every code, or search stand-out terms like **'food'**, **'history'**, **'law'**."
                )

            # Ensure these two lines are properly indented INSIDE the `if prompt := st.chat_input(...)` block:
            st.session_state.chat_messages.append({"role": "assistant", "content": response_text})
            st.rerun()