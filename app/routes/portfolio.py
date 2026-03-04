import streamlit as st
import pandas as pd
import plotly.express as px
from app.utils import get_data, save_data, log_activity
from app.logic import calculate_metrics, get_broker_commission
from app import config

def show():
    st.title("💼 Current Portfolio")
    df = get_data("portfolio.csv")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("Portfolio is empty.")

