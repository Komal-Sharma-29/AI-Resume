import streamlit as st
import google.generativeai as genai
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
import re
import random
import pdfplumber
import mysql.connector
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime

# --- DATABASE CONNECTION ---
def get_db_connection():
    try:
        return mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            port=int(st.secrets["mysql"]["port"]),
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"],
            buffered=True
        )
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return None

def init_db():
    conn= get_db_connection()
    if conn:
        cursor=conn.cursor()
        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS candidates (
                                id INT AUTO_INCREMENT PRIMARY KEY,
                                name VARCHAR(255),
                                email VARCHAR(255),
                                skills VARCHAR(255),
                                match_score FLOAT,
                                job_title VARCHAR(255),
                                company VARCHAR(255),
                                experience_years INT
                            )
                        """)
        conn.commit()
        cursor.close()
if name=="main":
    init_db()

def verify_login(username, password, role_selected):
    conn = get_db_connection()
    if conn is None:
        return None
    
    try:
        cursor = conn.cursor(dictionary=True)
        if role_selected == "Candidate (User)":
            query = "SELECT * FROM users WHERE username = %s AND password = %s AND role = %s"
            cursor.execute(query, (username, password, role_selected))
        else:
            query = "SELECT * FROM admins WHERE username = %s AND password = %s" 
            cursor.execute(query, (username, password))
            
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        return result
    except Exception as e:
        st.error(f"❌ Login Query Error: {e}")
        return None


def extract_contact_info(text):
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    email_match = re.search(email_pattern, text)
    email = email_match.group(0) if email_match else ""

    phone_pattern = r'\b\d{10}\b|\+?\d{1,3}[-.\s]?\d{10}\b'
    phone_match = re.search(phone_pattern, text)
    phone = phone_match.group(0) if phone_match else ""

    return email, phone


def get_local_interview_question(missing_skills):
    question_bank = {
        "Python": [
            "Explain the difference between a List and a Tuple in Python. When would you use which?",
            "What are decorators in Python and how do they work?",
            "What is the difference between deep copy and shallow copy in Python?"
        ],
        "Sql": [
            "What is the difference between WHERE and HAVING clauses in SQL? Give an example.",
            "Explain Left Join, Right Join, and Inner Join with examples.",
            "What are primary keys and foreign keys in a database?"
        ],
        "Html": [
            "What are semantic tags in HTML5, and why are they important for SEO?",
            "What is the difference between block-level and inline elements?"
        ],
        "Css": [
            "Explain the difference between 'position: relative' and 'position: absolute' in CSS.",
            "What is the CSS Box Model? Explain its components."
        ],
        "Javascript": [
            "What is the difference between '==' and '===' operators in JavaScript?",
            "Explain the concept of closures in JavaScript."
        ],
        "Machine learning": [
            "What is overfitting in Machine Learning, and how can you prevent it?",
            "What is the difference between supervised and unsupervised learning?"
        ],
        "Streamlit": [
            "How does Streamlit handle state retention across reruns? What is st.session_state?",
            "What is the use of @st.cache_data and @st.cache_resource in Streamlit?"
        ]
    }
    
  
    available_pool = []
    for skill in missing_skills:
        if skill in question_bank:
            available_pool.extend(question_bank[skill])        
    if available_pool:
        return random.choice(available_pool)
    generic_questions = [
        "What is OOPs (Object-Oriented Programming) and explain its 4 core pillars.",
        "What is a constructor in programming and why is it used?",
        "Explain the difference between a class and an object."
    ]
    return random.choice(generic_questions)


def evaluate_local_answer(user_answer):
    word_count = len(user_answer.split())
    if word_count < 10:
        return "⚠️ **Score: 3/10**\n\n**Feedback:** Your answer is too short. Please provide a detailed technical explanation with examples.", "error"
    elif word_count < 30:
        return "📊 **Score: 6/10**\n\n**Feedback:** Good basic attempt, but you missed deeper technical insights. Try expanding your points.", "warning"
    else:
        return "✅ **Score: 8.5/10**\n\n**Feedback:** Excellent structure and comprehensive response! You explained the concepts clearly.", "success"

st.set_page_config(page_title="AI Resume Analyser & Insight Hire", layout="wide", page_icon="🤖")

def calculate_experience_from_resume(text):
    import re
    from datetime import datetime
    
    clean_text = " ".join(text.lower().split())
    
    # --- STRICT SECTION VALIDATION ---
    work_keywords = ["work experience", "employment history", "professional experience", "job history", "internship experience"]
    has_work_profile = any(kw in clean_text for kw in work_keywords)
    
    if not has_work_profile:
        return 0  

    current_year = datetime.now().year
    years = [int(y) for y in re.findall(r'\b(20[0-2]\d|19\d{2})\b', clean_text)]
    has_present = any(p in clean_text for p in ["present", "current", "till date"])
    if has_present:
        years.append(current_year)
        
    if not years:
        return 0    
        
    years = sorted(list(set(years)))
    
    regex_ranges = re.findall(r'\b(20[0-2]\d|19\d{2})\s*(?:-|to|until)\s*(20[0-2]\d|19\d{2}|present|current)\b', clean_text)
    
    if regex_ranges:
        calculated_years = 0
        for start, end in regex_ranges:
            try:
                s_yr = int(start)
                e_yr = current_year if end in ['present', 'current'] else int(end)
                if e_yr >= s_yr and (e_yr - s_yr) < 15:
                    calculated_years += (e_yr - s_yr)
            except:
                continue
        if calculated_years > 0:
            return min(calculated_years, 25)

    return 0

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"],.main {
        font-family: 'Poppins', sans-serif!important;
    }
    
    h1 {
        font-family: 'Poppins', sans-serif!important;
        font-weight: 700!important;
        text-align: center!important;
        padding-top: 10px;
        padding-bottom: 5px;
        color: inherit!important;
    }
    
    h2, h3, h4, h5, h6 {
        font-family: 'Poppins', sans-serif!important;
        font-weight: 600!important;
        color: inherit!important;
    }

    [data-testid="stFileUploader"] {
        font-family: 'Poppins', sans-serif!important;
    }
    
    [data-testid="stFileUploader"] label {
        display: block!important;
        font-family: 'Poppins', sans-serif!important;
        font-weight: 500!important;
        margin-bottom: 10px!important;
        visibility: visible!important;
    }

    [data-testid="stFileUploader"] section {
        padding: 15px!important;
    }
    
    [data-testid="stFileUploader"] section div[data-testid="stMarkdownContainer"] p::before {
        display: none!important;
    }
    
    [data-testid="stFileUploader"] section p {
        text-align: left!important;
        display: inline-block!important;
        margin: 0 5px!important;
    }

    [data-testid="column"]{
        overflow-wrap: break-word !important;
        word-break: break-word !important;
        white-space: normal !important;
    }

    label, p {
        font-family: 'Poppins', sans-serif!important;
        white-space: normal !important;
    }

   .stMetric { background: #f8f9fa !important; padding: 20px !important; border-radius: 15px !important; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-top: 5px solid #00d2ff !important; }
    div[data-testid="stExpander"] { background: #f8f9fa; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    
   .skill-tag { background: #e3f2fd; color: #0d47a1; padding: 6px 15px; border-radius: 20px; margin: 3px; display: inline-block; font-weight: 600; font-size: 13px; }
   .missing-tag { background: #ffebee; color: #b71c1c; padding: 6px 15px; border-radius: 20px; margin: 3px; display: inline-block; font-weight: 600; font-size: 13px; }
   .stButton>button { border-radius: 30px !important; height: 3em !important; background: linear-gradient(45deg, #00d2ff, #3a7bd5) !important; color: white !important; border: none !important; font-weight: bold !important; width: 100% !important; }
    </style>
""", unsafe_allow_html=True)


if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'user_info' not in st.session_state:
    st.session_state.user_info = None

# --- AUTHENTICATION GATEKEEPER ---
if not st.session_state.logged_in:
    st.title("LOGIN")
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        username_input = st.text_input("Username", key="login_username_field")
        password_input = st.text_input("Password", type="password", key="login_password_field")
        login_as = st.selectbox("Login As:",["Candidate (User)", "HR Recruiter (Admin)"], key="login_role_selectbox")

        if st.button("Sign In", use_container_width=True):
            if username_input and password_input:
                user_data = verify_login(username_input, password_input, login_as)
                
                if user_data:
                    st.success(f"Welcome {username_input}!")
                    st.session_state.logged_in = True
                    st.session_state.user_info = user_data
                    if login_as == "Candidate (User)":
                        st.session_state.user_role = "user"
                    else:
                        st.session_state.user_role = "admin"
                    st.rerun() 
                else:
                    st.error("❌ Invalid Username, Password, or Role selected!")
            else:
                st.warning("⚠️ Please enter both Username and Password")

        st.write("")

        with st.expander("Don't have an account? Sign Up"):
            new_user = st.text_input("New Username", key="reg_user")
            new_pass = st.text_input("New Password", type="password", key="reg_pass") 
            new_full_name = st.text_input("Full Name", key="reg_name")
            new_email = st.text_input("Email Address", key="reg_email")
            new_phone = st.text_input("Phone Number", key="reg_phone")
            new_role = st.selectbox("Select Role", ["Candidate (User)", "HR (Admin)"], key="reg_role")
            
            admin_authenticated = True
            if new_role == "HR (Admin)":
                admin_passcode = st.text_input("Enter Secret Admin Registration Key", type="password", key="reg_admin_key")
                
                if admin_passcode != "SUPER_SECRET_HR_2026":
                    admin_authenticated = False
            
           
            r_col1, r_col2, r_col3 = st.columns([1.5, 1, 1.5])
            with r_col2:
                register_btn = st.button("Register", use_container_width=True)
                
            if register_btn:
                if new_user and new_pass:
                    if new_role == "HR (Admin)" and not admin_authenticated:
                        st.error("❌ Invalid Admin Registration Key! You are not authorized to create an Admin account.")
                    else:
                        conn = get_db_connection()
                        if conn:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("""
                                        CREATE TABLE IF NOT EXISTS users (
                                            id INT AUTO_INCREMENT PRIMARY KEY,
                                            full_name VARCHAR(255),
                                            email VARCHAR(255),
                                            phone VARCHAR(10),
                                            username VARCHAR(255),
                                            password VARCHAR(255),
                                            role VARCHAR(20)
                                        )
                                    """)
                                cursor.execute("""
                                   CREATE TABLE IF NOT EXISTS admins(
                                       id INT AUTO_INCREMENT PRIMARY KEY,
                                        username VARCHAR(255),
                                        password VARCHAR(255),
                                        role VARCHAR(20)
                                    )
                                """)
                                conn.commit()
                            
                                if new_role == "Candidate (User)":
                                    query = "INSERT INTO users (username, password, full_name, email, phone, role) VALUES (%s, %s, %s, %s, %s, %s)"
                                    cursor.execute(query, (new_user, new_pass, new_full_name, new_email, new_phone, new_role))
                                else:
                                    query = "INSERT INTO admins (username, password) VALUES (%s, %s)"
                                    cursor.execute(query, (new_user, new_pass))
                                conn.commit()
                                cursor.close()
                                conn.close()
                                st.success("🎉 Account successfully created! Please log in above.")
                            except Exception as e:
                                st.error(f"Error creating account: {e}")
                else:
                    st.warning("Please fill all details.")


# AFTER SUCCESSFUL LOGIN
else:
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/2103/2103633.png", width=80)
        st.title("Project Navigation")
        st.title("User Profile")
        if 'user_info' in st.session_state:
            info = st.session_state.user_info
            if isinstance(info, dict):
                username = info.get('username', 'User')
                st.write(f"Logged in as: **{username.upper()}**")
            else:
                st.write("Please log in.")
        else:
            st.write("Please log in.")
       # st.write(f"Logged in as: **{st.session_state.user_info['username'].upper()}**")

        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_role = None
            st.session_state.user_info = None
            st.rerun()

    # --- 👤 CANDIDATE / USER PORTAL ---
    if st.session_state.user_role == "user":
        st.title("Resume Analyser & Roadmap using AI")
        st.markdown("<p style='text-align: center; font-family: Poppins, sans-serif;'>Analyze your skills and find out what you should learn next</p>", unsafe_allow_html=True)

        if 'ext_name' not in st.session_state: st.session_state.ext_name = ""
        if 'ext_email' not in st.session_state: st.session_state.ext_email = ""
        if 'ext_phone' not in st.session_state: st.session_state.ext_phone = ""
        
        if 'analysis_done' not in st.session_state: st.session_state.analysis_done = False
        if 'missing_skills' not in st.session_state: st.session_state.missing_skills =[]
        if 'match_score' not in st.session_state: st.session_state.match_score = 0
        if 'found_skills' not in st.session_state: st.session_state.found_skills =[]
        if 'resume_text_saved' not in st.session_state: st.session_state.resume_text_saved = ""
        
        if 'local_question' not in st.session_state: st.session_state.local_question = ""
        if 'local_feedback' not in st.session_state: st.session_state.local_feedback = ""
        if 'local_fb_type' not in st.session_state: st.session_state.local_fb_type = ""
        
        def click_generate_question():
            if st.session_state.missing_skills:
                st.session_state.local_question = get_local_interview_question(st.session_state.missing_skills)
            else:
                st.session_state.local_question = "What is OOPs (Object-Oriented Programming) and explain its 4 core pillars."
            st.session_state.local_feedback = ""

        col1, col2 = st.columns([1, 1], gap="large")
        with col1:
            jd_text = st.text_area("Paste Job Description (JD) here.", height=150, placeholder="Example: Looking for a Python developer with SQL and Streamlit skills.")
        with col2:
            u_file = st.file_uploader("Upload PDF Resume here.", type=["pdf"])
            if u_file:
                st.success("Resume Uploaded Successfully!")

            if u_file:
                if 'last_uploaded_file' not in st.session_state or st.session_state.last_uploaded_file!= u_file.name:
                    with pdfplumber.open(u_file) as pdf:
                        first_page_lines = pdf.pages[0].extract_text().split('\n') if pdf.pages else []
                        resume_text = " ".join([page.extract_text() for page in pdf.pages]).lower()
                    
                    extracted_name = ""
                    if first_page_lines:
                        for line in first_page_lines:
                            clean_line = line.strip()
                            if clean_line and len(clean_line) > 2 and not any(char.isdigit() for char in clean_line) and "@" not in clean_line:
                                extracted_name = clean_line.title()
                                break
                    
                    if not extracted_name:
                        raw_filename = u_file.name.split('.')[0]
                        extracted_name = raw_filename.replace('_', ' ').replace('-',' ').title()
                    
                    email, phone = extract_contact_info(resume_text)
                    extracted_exp = calculate_experience_from_resume(resume_text)
                    
                    st.session_state.ext_name = extracted_name
                    st.session_state.ext_email = email
                    st.session_state.ext_phone = phone 
                    st.session_state.ext_experience = int(extracted_exp)
                    st.session_state.last_uploaded_file = u_file.name
                    st.rerun()

                if 'ext_name' in st.session_state:
                    st.success("AI has autofilled your contact info!")
                    c_form1, c_form2, c_form3 = st.columns([1.2, 1.5, 1.2])
                    with c_form1:
                        u_name = st.text_input("Full Name", value=st.session_state.ext_name)
                    with c_form2:
                        u_email = st.text_input("Email ID", value=st.session_state.ext_email)
                    with c_form3:
                        u_phone = st.text_input("Phone Number", value=st.session_state.ext_phone)

                    st.markdown("Past Work Experience")
                    exp_col1, exp_col2, exp_col3 = st.columns([1.5, 1.2, 1.2])
                    with exp_col1:
                        u_job = st.text_input("Most Recent Job Title", placeholder="e.g., Frontend Intern")
                    with exp_col2:
                        u_company = st.text_input("Company Name", placeholder="e.g., Tech Solutions Inc.")
                    with exp_col3:
                        u_exp_years = st.number_input("Years of Experience", min_value=0, max_value=25, value=int(st.session_state.get('ext_experience',0)), key=f"force_refresh_{u_file.name}")

        # --- REFRESHED MAIN ANALYSIS MATCHING ---
        if st.button("Analyze your resume and find your roadmap"):
            if u_file and jd_text and u_name and u_email:
                with st.spinner("Analyzing your profile..."):
                    with pdfplumber.open(u_file) as pdf:
                        resume_text = " ".join([page.extract_text() for page in pdf.pages]).lower()
                    
                    tech_stack = ["python", "sql", "html", "css", "javascript", "machine learning", "streamlit", "react", "java", "aws", "data science", "C", "C++","Fortran"]
                    found = [s.capitalize() for s in tech_stack if s in resume_text]
                    required_in_jd = [s.capitalize() for s in tech_stack if s in jd_text.lower()]
                    missing = [s for s in required_in_jd if s not in found]

                    if len(required_in_jd) > 0:
                        score = round((len(found) / len(required_in_jd)) * 100, 2)
                        score = min(float(score), 100.0) 
                    else:
                        score = 0.0
                    
                    verified_experience = calculate_experience_from_resume(resume_text)

                    total_required_skills = len(found) + len(missing)
                    if total_required_skills > 0:
                        weight_per_missing = 100 / total_required_skills
                        skill_penalty = len(missing) * weight_per_missing
                        keyword_matrix_score = 100 - skill_penalty
                        final_user_score = (score + keyword_matrix_score) / 2
                    else:
                        final_user_score = score
                        
                    if len(missing) > 0 and final_user_score >= 95.0:
                        final_user_score = 100.0 - (len(missing) * 12.5)
                        
                    final_user_score = max(0.0, min(100.0, final_user_score))
                    final_user_score = round(final_user_score, 1)

                    st.session_state.missing_skills = missing
                    st.session_state.match_score = final_user_score  
                    st.session_state.found_skills = found
                    st.session_state.resume_text_saved = resume_text
                    st.session_state.analysis_done = True

                    # SQL SERVER DISPATCH
                    conn = get_db_connection()
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO candidates (name, email, skills, match_score, job_title, company, experience_years) VALUES (%s,%s,%s,%s,%s,%s,%s)", 
                                    (u_name, u_email, ", ".join(found), final_user_score, u_job, u_company, int(verified_experience)))
                        conn.commit()
                        conn.close()
                    st.balloons()
            else:
                st.error("Please fill all details and upload your resume.")

        # DISPLAY RESULTS
        if st.session_state.analysis_done:
            st.divider()

            user_base_score = float(st.session_state.match_score)
            user_found_list = st.session_state.found_skills
            user_missing_list = st.session_state.missing_skills

            total_required_skills = len(user_found_list) + len(user_missing_list)

            if total_required_skills > 0:
                weight_per_missing_skill = 100 / total_required_skills
                skill_penalty = len(user_missing_list) * weight_per_missing_skill
                keyword_matrix_score = 100 - skill_penalty
                final_user_score = (user_base_score + keyword_matrix_score) / 2
            else:
                final_user_score = user_base_score

            if len(user_missing_list) > 0 and final_user_score >= 95.0:
                final_user_score = 100.0 - (len(user_missing_list) * 12.5)

            final_user_score = max(0.0, min(100.0, final_user_score))
            final_user_score = round(final_user_score, 1)

            st.subheader("ATS Compatibility Rating")
            fig_gauge = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = final_user_score,  
                domain = {'x':[0, 1] , 'y':[0, 1] },
                gauge = {
                    'axis': {'range': [None, 100]},
                    'bar': {'color': "#3a7bd5"},
                    'steps': [
                        {'range':[0, 40] , 'color': "#ff8a80"},
                        {'range':[40, 75] , 'color': "#ffd740"},
                        {'range':[75, 100] , 'color': "#b9f6ca"}
                    ],
                }
            ))
            fig_gauge.update_layout(height=240, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_gauge, use_container_width=True)

            st.subheader(f"Your Match Score: {final_user_score}%")

            c1, c2 = st.columns(2)
            with c1:
                st.write("**Skills Found in Your Resume:**")
                if st.session_state.found_skills:
                    for s in st.session_state.found_skills: st.markdown(f'<span class="skill-tag">{s}</span>', unsafe_allow_html=True)
                else: st.write("No technical skills detected.")
            with c2:
                st.write("**Missing Skills:**")
                if st.session_state.missing_skills:
                    for m in st.session_state.missing_skills: st.markdown(f'<span class="missing-tag">{m}</span>', unsafe_allow_html=True)
                else: st.success("All Skill is matched! Perfect Match.")

            st.divider()
            st.subheader("Resume Keyword Density")
            if st.session_state.resume_text_saved:
                wordcloud = WordCloud(width=800, height=300, background_color='white', max_words=30, colormap='Blues').generate(st.session_state.resume_text_saved)
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.imshow(wordcloud, interpolation='bilinear')
                ax.axis('off')
                st.pyplot(fig)

            st.divider()
            st.subheader("Recommended Learning Path")
            if st.session_state.missing_skills:
                st.warning(f"Your score is {final_user_score}%. You can make it 100% by learning these skills:")
                for m in st.session_state.missing_skills:
                    st.write(f"**{m} Tutorial:**(https://www.youtube.com/results?search_query=learn+{m.lower()}+for+beginners)")

            st.subheader("Job Recommendation")
            primary_skill = st.session_state.found_skills if st.session_state.found_skills else "Software Developer"
            st.markdown(f"[Find {primary_skill} Jobs on LinkedIn](https://www.linkedin.com/jobs/search/?keywords={primary_skill})")

            st.divider()
            st.subheader("Mock Interview Coach")
            st.write("The system will ask you questions based on your missing skills.")

            st.button("Generate Interview Question", key="Local_gen_btn", on_click=click_generate_question)

            if st.session_state.local_question:
                st.info(f"**Interviewer:** {st.session_state.local_question}")

                with st.form(key='interview_response_form'):
                    user_ans = st.text_area("Type your detailed answer here:", height=100, key="local_ans_box")
                    submit_ans = st.form_submit_button("Submit Answer for Evaluation")

                    if submit_ans:
                        if user_ans:
                            feedback_text, status_type = evaluate_local_answer(user_ans)
                            st.session_state.local_feedback = feedback_text
                            st.session_state.local_fb_type = status_type
                        else:
                            st.error("First type your answer in the box!")

            if st.session_state.local_feedback:
                st.divider()
                if st.session_state.local_fb_type == "success": st.success(st.session_state.local_feedback)
                elif st.session_state.local_fb_type == "warning": st.warning(st.session_state.local_feedback)
                else: st.error(st.session_state.local_feedback)

    # --- 🛠️ HR / ADMIN PORTAL ---
    elif st.session_state.user_role == "admin":
        st.title("HR Recruitment Analytics Dashboard")
        st.markdown("<p style='text-align: center; font-family: Poppins, sans-serif;'>Track the lists of candidates and their performance here.</p>", unsafe_allow_html=True)
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import re

        admin_jd = st.text_area(
            "Job Description from HR. Paste the Job Description (JD) here.",
            placeholder="e.g., Requirements: Python, SQL, Machine Learning, Data Structures...",
            height=150
        )

        filtered_df = pd.DataFrame()

        if not admin_jd:
            st.info("Status: Awaiting Job Description. Please paste a JD above.")
        else:
            st.success("Job Description Registered!")
            st.divider()

            with st.sidebar:
                st.header("Filters:")
                min_score = st.slider("Min match score (%)", 0, 100, 0)
                min_exp = st.slider("Minimum Experience (Years)", 0, 20, 0)
                skill_filter = st.text_input("Search by skill (e.g., Python)")
                st.divider()

            conn = get_db_connection()
            cursor = conn.cursor(buffered=True)
            if conn:
                query = """
                SELECT c.*, u.email as user_email 
                FROM candidates c 
                LEFT JOIN users u ON c.name = u.full_name
                """
                if conn is None or not conn.is_connected():
                    conn = get_db_connection()
                df = None
                cursor = conn.cursor(buffered=True)
                try:
                    df = pd.read_sql(query, conn)
                    cursor.close()
                except Exception as e:
                    st.error(f"Database error: {e}")
                    conn.close()

                if df is not None and not df.empty:
                    if 'experience_years' in df.columns:
                        df['experience_years'] = pd.to_numeric(df['experience_years'], errors='coerce').fillna(0).astype(int)
                    else:
                        df['experience_years'] = 0

                    recalculated_scores =[]
                    tech_stack = ["python", "sql", "html", "css", "javascript", "machine learning", "streamlit", "react", "java", "aws", "data science", "C", "C++", "Fortran"]
                    required_in_admin_jd = [s.capitalize() for s in tech_stack if s in admin_jd.lower()]

                    for idx, row in df.iterrows():
                        candidate_skills_str = str(row['skills']) if row['skills'] else ""
                        candidate_skills_list = [s.strip().capitalize() for s in candidate_skills_str.split(", ") if s.strip()]

                        if required_in_admin_jd and candidate_skills_list:
                            matched_skills = [s for s in required_in_admin_jd if s in candidate_skills_list]
                            match_pct = round((len(matched_skills) / len(required_in_admin_jd)) * 100, 2)
                            match_pct = min(float(match_pct), 100.0)
                        else:
                            match_pct = 0.0

                        recalculated_scores.append(match_pct)

                    df['match_score'] = recalculated_scores

                    filtered_df = df.copy()
                    
                    columns_to_clean = ['job_title', 'company']
                    for col in columns_to_clean:
                        if col in filtered_df.columns:
                            filtered_df[col] = filtered_df[col].replace(['None', 'none', 'NaN', 'nan'], pd.NA)
                            filtered_df[col] = filtered_df[col].replace(r'^\s*$', pd.NA, regex=True)
                            filtered_df[col] = filtered_df[col].fillna("Not Specified")

                    valid_indices = df[
                        (df['match_score'] >= min_score) &
                        (df['experience_years'] >= min_exp)
                    ].index

                    filtered_df = filtered_df.loc[valid_indices]

                    if not filtered_df.empty and 'experience_years' in filtered_df.columns:
                        filtered_df['experience_years'] = filtered_df['experience_years'].astype(str).replace(['0', '0.0'], 'Fresher')

                    with st.sidebar:
                        st.subheader("Leaderboard ")
                        top_n_candidate = st.slider("Select Top Candidates", 0, 20, 0)
                        st.divider()

                    if skill_filter and not filtered_df.empty and 'skills' in filtered_df.columns:
                        filtered_df = filtered_df[filtered_df['skills'].str.contains(skill_filter, case=False, na=False)]

                    if not filtered_df.empty:
                        sorted_leaderboard = filtered_df.sort_values(by="match_score", ascending=False)

                        if top_n_candidate > 0:
                            sorted_leaderboard = sorted_leaderboard.head(top_n_candidate)
                            chart_title = f"Top {len(sorted_leaderboard)} Candidate Match Comparison"
                        else:
                            chart_title = "All Qualified Candidates Match Comparison"

                        st1, st2, st3 = st.columns(3)
                        st1.metric("Total Resumes Analyzed", len(sorted_leaderboard))
                        st2.metric("Average Match Score", f"{round(sorted_leaderboard['match_score'].mean(), 2)}%")
                        st3.metric("Highest Score", f"{sorted_leaderboard['match_score'].max()}%")

                        st.subheader("Candidate Analysis")
                        fig = px.bar(sorted_leaderboard,
                                     x="name", y="match_score", color="match_score",
                                     title=chart_title,
                                     color_continuous_scale="Plasma",
                                     labels={'match_score': 'Recalculated Score (%)', 'name': 'Candidate Name'})
                        fig.update_layout(yaxis_range=[0, 100])
                        st.plotly_chart(fig, use_container_width=True)

                        st.subheader("List of Candidates")

                        display_cols = ['id', 'name', 'email', 'skills', 'match_score', 'experience_years', 'job_title', 'company']
                        available_cols = [c for c in display_cols if c in sorted_leaderboard.columns]

                        for idx, row in sorted_leaderboard.iterrows():
                            with st.container():
                                col1, col2, col3, col4 = st.columns([0.5, 1.5, 2, 1.5])

                                with col1:
                                    st.write(f"**ID: {row['id']}**")
                                with col2:
                                    st.write(f"👤 **{row['name']}**")
                                    st.caption(f"Score: {row['match_score']}% | Experience: {row['experience_years']}")
                                with col3:
                                    st.write(f"{row['skills'][:50]}...")
                                    st.caption(f"Role: {row['job_title']} at {row['company']}")
                                with col4:
                                    email_id = row['email']
                                    candidate_name = row['name']
                                    match_score = row['match_score']

                                    button_key = f"email_btn_{row['id']}_{idx}"

                                    @st.dialog(f"Send Offer/Interview Letter to {candidate_name}")
                                    def send_email_popup(c_email, c_name, c_score):
                                        if not c_email or c_email == "None":
                                            st.error(f"⚠️ Email address nahi mila {c_name} ke liye. User profile check karein.")
                                            return
                                        
                                        st.write(f"**To Candidate:** {c_name} (`{c_email}`)")
                                        st.caption(f"Profile Match Core Matrix Score: {c_score}%")
                                        st.divider()

                                        hr_email = st.text_input("Enter your HR / Sender Gmail Address", placeholder="hr.company@gmail.com")
                                        hr_password = st.text_input("Enter your 16-digit Google App Password", type="password", help="Do not enter your regular login password. Use a Google App Password.")

                                        st.subheader("Edit Email Content Template")
                                        custom_subject = st.text_input("Subject", value="Interview Invitation - HR Recruitment Analytics System")
                                        custom_body = st.text_area("Email Body", value=f"Hello {c_name},\n\nWe reviewed your profile matching score ({c_score}%) for our structural job requirements and we are pleased to invite you for an interview sequence.In case of any queries contact to the company directly. \n\nBest Regards,\nHR Team Server", height=150)

                                        if st.button("Dispatch Letter Now", use_container_width=True):
                                            if not hr_email or not hr_password:
                                                st.error("Sender Credentials cannot be left blank.")
                                            else:
                                                import smtplib
                                                from email.mime.text import MIMEText
                                                from email.mime.multipart import MIMEMultipart

                                                msg = MIMEMultipart()
                                                msg['From'] = hr_email
                                                msg['To'] = c_email
                                                msg['Subject']= custom_subject
                                                msg.attach(MIMEText(custom_body, 'plain'))

                                                try:
                                                    with st.spinner("Establishing secure relay connection..."):
                                                        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
                                                        server.login(hr_email, hr_password)
                                                        server.sendmail(hr_email, c_email, msg.as_string())
                                                        server.quit()
                                                    st.success(f"Letter dispatched successfully to {c_name}!")
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"Connection Failed: Check your email or 16-digit app password layout.")

                                    if st.button("📧 Send Email", key=button_key, use_container_width=True):
                                        send_email_popup(email_id, candidate_name, match_score)
                                st.divider()

                        st.download_button("Download Recruitment Report (CSV)",
                                           sorted_leaderboard[available_cols].to_csv(index=False),
                                           file_name="candidate_report.csv")
                    else:
                        st.warning("No records found match according to the given criteria or entered Job Description parameters.")
