import streamlit as st
from app import config, utils, logic
from app.routes import dashboard, portfolio, tms

# 1. Initialize App Configuration
config.init_config()
config.apply_custom_css()

# 2. Enforce Authentication
if not utils.check_login():
    st.stop()

# 3. Sidebar Navigation
with st.sidebar:
    st.header("🚀 NEPSE Pro")
    menu = st.radio("Main Menu", ["Dashboard", "My TMS", "Portfolio"])

    st.divider()
    if st.button("🔄 Sync Market Data"):
        if logic.refresh_market_cache():
            logic.update_wealth_log()
            st.rerun()

# 4. Route Handling
if menu == "Dashboard":
    dashboard.show()
elif menu == "My TMS":
    tms.show()
elif menu == "Portfolio":
    portfolio.show()
