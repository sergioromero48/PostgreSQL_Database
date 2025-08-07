import streamlit as st
import pandas as pd
from database import get_conn
from serial_worker import start_worker

st.set_page_config(page_title="ESP32 Weather", layout="wide")
start_worker()                       # kick off background thread once

st.title("📡 ESP32 Weather Dashboard")

with st.spinner("Loading latest data…"):
    conn = get_conn()
    df = pd.read_sql(
        "SELECT * FROM weatherDataFromSite1 "
        "ORDER BY EntryTime DESC LIMIT 100", conn
    )

if df.empty:
    st.info("Waiting for first packets…")
    st.stop()

# ---- UI ----
col1, col2 = st.columns(2)

with col1:
    st.subheader("Raw table")
    st.dataframe(df, use_container_width=True)

with col2:
    st.subheader("Water-level trend")
    st.line_chart(
        df.set_index("EntryTime")["WaterLevel"]
          .replace({"Low":0,"Nominal":1,"High":2})
    )

st.caption("Auto-refresh with the ↻ button in the toolbar.")
