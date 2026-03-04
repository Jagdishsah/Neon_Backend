import streamlit as st
import pandas as pd
import plotly.express as px
from app.utils import get_data, save_data, log_activity
from app.logic import calculate_metrics, get_broker_commission
from app import config

def show():
    st.title("📊 Portfolio Dashboard")
    port_df = get_data("portfolio.csv")
    cache_df = get_data("cache.csv")
    if port_df.empty:
        st.info("No holdings found. Start by adding trades in 'My TMS'.")
        return
    inv, val, pl, pct = calculate_metrics(port_df, cache_df)
    col1, col2, col3 = st.columns(3)
    col1.metric("Invested", f"Rs. {inv:,.2f}")
    col2.metric("Current Value", f"Rs. {val:,.2f}")
    col3.metric("Net P/L", f"Rs. {pl:,.2f}", f"{pct:.2f}%")

