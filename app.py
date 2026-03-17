import streamlit as st
import importlib

# Ensure the page stretches to full width
st.set_page_config(page_title="NEPSE Pro Terminal", layout="wide")

# ==========================================
# 1. AUTHENTICATION SYSTEM (Mock Database)
# Note: In production, put passwords in .streamlit/secrets.toml
# ==========================================
USERS = {
    "admin": {"password": "adminpassword", "role": "Admin"},
    "guest": {"password": "viewpassword", "role": "View Only"}
}

def login_screen():
    st.title("🏦 NEPSE Pro Terminal Login")
    
    with st.form("login_form"):
        username = st.text_input("Username").strip().lower()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        
        if submitted:
            if username in USERS and USERS[username]["password"] == password:
                st.session_state["logged_in"] = True
                st.session_state["role"] = USERS[username]["role"]
                st.session_state["username"] = username
                st.rerun()  # Instantly refresh to clear the login screen
            else:
                st.error("Invalid Username or Password")

# Initialize session state for security
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

# ==========================================
# 2. MAIN APPLICATION ROUTER
# ==========================================
def main_app():
    # --- Sidebar Navigation ---
    st.sidebar.title("NEPSE Pro Terminal")
    st.sidebar.caption(f"Logged in as: **{st.session_state['username'].capitalize()}** ({st.session_state['role']})")
    
    if st.sidebar.button("Logout"):
        st.session_state["logged_in"] = False
        st.session_state["role"] = None
        st.session_state["username"] = None
        st.rerun()

    st.sidebar.divider()

    # The list of your exact requested tabs
    menu_options = [
        "Dashboard", "My TMS", "Portfolio", "Watchlist", 
        "Nepse Data Analysis", "Add Trade", "Sell Stock", 
        "History", "Activity Log", "Wealth Graph", 
        "WACC Projection", "What If Analysis", "Reports", 
        "Manage Data", "Trading Journal", "Risk Manager"
    ]
    
    selected_tab = st.sidebar.radio("Main Menu", menu_options)
    
    st.sidebar.divider()
    
    # --- Sync Utility Button ---
    if st.sidebar.button("🔄 Sync Now", use_container_width=True):
        with st.spinner("Syncing Database..."):
            # Dynamically import and run the sync utility
            from Utility import Sync
            Sync.run_sync()
            st.sidebar.success("Sync Complete!")

    # --- Dynamic Page Loading ---
    # We convert the menu name (e.g. "Add Trade") to the filename format (e.g. "Add_Trade")
    module_name = selected_tab.replace(" ", "_")
    
    try:
        # This dynamically imports the file from the Tabs folder
        page_module = importlib.import_module(f"Tabs.{module_name}")
        
        # We pass the user's role to the page so it can disable buttons if they are "View Only"
        page_module.render_page(role=st.session_state["role"])
        
    except ModuleNotFoundError:
        st.warning(f"🚧 The module `Tabs/{module_name}.py` has not been created yet.")
    except AttributeError:
        st.error(f"❌ `Tabs/{module_name}.py` must contain a function named `render_page(role)`.")

# ==========================================
# 3. APP EXECUTION
# ==========================================
if not st.session_state["logged_in"]:
    login_screen()
else:
    main_app()
