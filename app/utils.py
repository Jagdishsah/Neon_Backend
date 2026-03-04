import streamlit as st
import pandas as pd
from github import Github
from io import StringIO
from datetime import datetime

# --- GITHUB ENGINE ---
def get_repo():
    try:
        token = st.secrets["github"]["token"]
        repo_name = st.secrets["github"]["repo_name"]
        g = Github(token)
        return g.get_repo(repo_name)
    except:
        st.error("❌ GitHub Connection Failed. Check Secrets.")
        return None

@st.cache_data(ttl=300) 
def get_data(filename):
    repo = get_repo()
    if not repo: return pd.DataFrame()
    try:
        content = repo.get_contents(f"data/{filename}")
        return pd.read_csv(StringIO(content.decoded_content.decode("utf-8")))
    except Exception as e:
        return pd.DataFrame()

def save_data(filename, df, message):
    repo = get_repo()
    if not repo: return
    try:
        content = repo.get_contents(f"data/{filename}")
        repo.update_file(f"data/{filename}", message, df.to_csv(index=False), content.sha)
    except Exception as e:
        st.error(f"❌ Failed to save {filename}: {e}")

# --- LOGGING ENGINE ---
def log_error(func_name, error_msg):
    try:
        err_df = get_data("error_log.csv")
        new_err = pd.DataFrame([{"Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Function": func_name, "Error": error_msg}])
        err_df = pd.concat([err_df, new_err], ignore_index=True)
        save_data("error_log.csv", err_df, f"Error in {func_name}")
    except: pass

def log_activity(category, symbol, action, details, amount=0):
    try:
        log_df = get_data("activity_log.csv")
        new_entry = pd.DataFrame([{
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Category": category, "Symbol": symbol, "Action": action, 
            "Details": details, "Amount": amount
        }])
        log_df = pd.concat([log_df, new_entry], ignore_index=True)
        save_data("activity_log.csv", log_df, f"Log: {action} {symbol}")
    except: pass

# --- AUTHENTICATION ENGINE ---
def check_login():
    if "login_correct" not in st.session_state:
        st.session_state["login_correct"] = False

    if not st.session_state["login_correct"]:
        st.header("🔒 NEPSE Pro Terminal")
        st.caption("Secure Access Required")
        with st.form("credentials_form"):
            user_input = st.text_input("Username")
            pass_input = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In", type="primary")
            if submitted:
                if (user_input == st.secrets["app_username"] and 
                    pass_input == st.secrets["app_password"]):
                    st.session_state["login_correct"] = True
                    st.rerun()
                else:
                    st.error("😕 Incorrect Username or Password")
        return False
    return True
