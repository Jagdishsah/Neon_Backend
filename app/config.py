import streamlit as st

# --- CONFIGURATION ---
def init_config():
    st.set_page_config(page_title="NEPSE Pro Terminal", page_icon="📈", layout="wide")

# Constants
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25
CGT_SHORT = 7.5 / 100
CGT_LONG = 5.0 / 100

# --- CUSTOM CSS ---
def apply_custom_css():
    st.markdown("""<style>
    .metric-card {background-color: #0E1117; border: 1px solid #262730; padding: 15px; border-radius: 5px; margin-bottom: 10px;}
    .stButton>button {width: 100%; border-radius: 5px;}
    .success-text {color: #00FF00;}
    .danger-text {color: #FF4B4B;}
    div.block-container {padding-top: 2rem;}
</style>""", unsafe_allow_html=True)
