# app.py — Flood Monitoring Dashboard (Streamlit)
import os
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from serial_worker import start_worker

# Optional: only used if you have Lat/Lon columns
try:
    from streamlit_folium import st_folium
    import folium
    HAS_MAP = True
except Exception:
    HAS_MAP = False

st.set_page_config(page_title="Flood Monitoring Dashboard", layout="wide")

# ------------------ config ------------------
CSV_PATH = Path(os.getenv("CSV_PATH", "data.csv"))
SITE_NAME = os.getenv("SITE_NAME", "Site 1")
# Alert thresholds (tweak to your setup)
LEVEL_MAP = {"Low": 0, "Nominal": 1, "High": 2}
LEVEL_ALERT_HIGH = 2                  # numeric level ≥ this => alert
RAIN_RATE_ALERT_IN_HR = 0.50         # in/hr
RAIN_24H_ALERT_IN = 2.00             # inches in last 24h
TEMP_ALERT_F = 95                    # °F
HUMIDITY_ALERT_PCT = 95              # %
# --------------------------------------------

# Kick off the serial → CSV background worker (non-fatal if it can't start)
try:
    start_worker()
    st.success("Background worker started")
except Exception as e:
    st.warning(f"Worker failed to start: {e}")

st.title("📡 Flood Monitoring")

# ---------------- Sidebar controls ----------------
with st.sidebar:
    st.markdown("### Controls")

    # Temperature unit toggle
    unit = st.radio("Temperature Unit", ["Fahrenheit (°F)", "Celsius (°C)"], index=0)
    to_c = (unit == "Celsius (°C)")

    # Date range filter (defaults last 72 hours)
    now = datetime.now()
    default_start = (now - timedelta(hours=72)).date()
    default_end = (now + timedelta(days=1)).date()
    start_date, end_date = st.date_input(
        "Date Range",
        [default_start, default_end],
        min_value=now.date() - timedelta(days=30),
        max_value=now.date() + timedelta(days=30),
        key="date_range",
    )

    # Rolling windows for rainfall
    st.markdown("#### Rain Windows")
    w_1h = st.number_input("1‑hour window (minutes)", min_value=30, max_value=180, value=60, step=5)
    w_3h = st.number_input("3‑hour window (minutes)", min_value=60, max_value=360, value=180, step=10)

# ---------------- Data load ----------------
with st.spinner("Loading data…"):
    if not CSV_PATH.exists():
        st.info("No data yet… waiting on ESP32.")
        st.stop()
    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        st.error(f"Failed to read {CSV_PATH}: {e}")
        st.stop()

if df.empty:
    st.info("No rows yet…")
    st.stop()

# Normalize columns & types
def _ensure_col(name): return name in df.columns

# Parse timestamps
if _ensure_col("EntryTime"):
    df["EntryTime"] = pd.to_datetime(df["EntryTime"], errors="coerce")
else:
    st.error("CSV missing 'EntryTime' column")
    st.stop()

# Numeric conversions
if _ensure_col("PrecipInInches"):
    df["PrecipInInches"] = pd.to_numeric(df["PrecipInInches"], errors="coerce")
if _ensure_col("HumidityInPercentage"):
    df["HumidityInPercentage"] = pd.to_numeric(df["HumidityInPercentage"], errors="coerce")
if _ensure_col("TemperatureInFahrenheit"):
    df["TemperatureInFahrenheit"] = pd.to_numeric(df["TemperatureInFahrenheit"], errors="coerce")

# Water level to numeric for plotting/alerts
if _ensure_col("WaterLevel"):
    df["LevelNum"] = df["WaterLevel"].map(LEVEL_MAP)

# Sort newest first
df = df.sort_values("EntryTime", ascending=False).reset_index(drop=True)

# Apply date filter (inclusive)
mask = (df["EntryTime"].dt.date >= start_date) & (df["EntryTime"].dt.date <= end_date)
fdf = df.loc[mask].copy()
if fdf.empty:
    st.info("No data in the selected range.")
    st.stop()

# Helpful time index
fdf = fdf.sort_values("EntryTime").reset_index(drop=True)
fdf = fdf.set_index("EntryTime")

# Temperature conversion
def to_display_temp_f_to_c(temp_f):
    if pd.isna(temp_f):
        return None
    return (temp_f - 32) * (5/9)

if _ensure_col("TemperatureInFahrenheit"):
    if to_c:
        fdf["TemperatureDisplay"] = fdf["TemperatureInFahrenheit"].apply(to_display_temp_f_to_c)
        temp_unit = "°C"
    else:
        fdf["TemperatureDisplay"] = fdf["TemperatureInFahrenheit"]
        temp_unit = "°F"

# Rolling rainfall calculations (assume `PrecipInInches` is event/instantaneous amount per sample)
if _ensure_col("PrecipInInches"):
    # 1h and 3h sums via fixed-minute rolling
    fdf["Rain_1h_in"] = fdf["PrecipInInches"].rolling(f"{w_1h}min").sum()
    fdf["Rain_3h_in"] = fdf["PrecipInInches"].rolling(f"{w_3h}min").sum()
    fdf["Rain_24h_in"] = fdf["PrecipInInches"].rolling("1440min").sum()
else:
    fdf["Rain_1h_in"] = None
    fdf["Rain_3h_in"] = None
    fdf["Rain_24h_in"] = None

# ---------------- Tabs ----------------
tab_rt, tab_trend, tab_map, tab_export = st.tabs(
    ["⚡ Real‑time & Alerts", "📈 Trends & History", "🗺️ Map & Meta", "📥 Export"]
)

# ---------- Real-time & Alerts ----------
with tab_rt:
    st.subheader(f"Real‑time status — {SITE_NAME}")

    latest = fdf.tail(1)

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        lvl_txt = latest["WaterLevel"].iloc[0] if _ensure_col("WaterLevel") and not latest["WaterLevel"].isna().all() else "—"
        st.metric("Water Level", f"{lvl_txt}")

    with c2:
        r1h = latest["Rain_1h_in"].iloc[0]
        st.metric("Rain (last 1h)", f"{r1h:.2f} in" if pd.notna(r1h) else "—")

    with c3:
        r24 = latest["Rain_24h_in"].iloc[0]
        st.metric("Rain (last 24h)", f"{r24:.2f} in" if pd.notna(r24) else "—")

    with c4:
        tdisp = latest["TemperatureDisplay"].iloc[0] if "TemperatureDisplay" in latest else None
        st.metric(f"Air Temp ({temp_unit})", f"{tdisp:.1f}" if pd.notna(tdisp) else "—")

    st.markdown("#### Alerts")
    any_alert = False

    # Water level alert
    if "LevelNum" in latest and pd.notna(latest["LevelNum"].iloc[0]):
        if latest["LevelNum"].iloc[0] >= LEVEL_ALERT_HIGH:
            st.error("🚨 Water level **HIGH**")
            any_alert = True

    # Rain rate alert: approx in/hr based on 1‑hour window sum
    if pd.notna(r1h) and r1h >= RAIN_RATE_ALERT_IN_HR:
        st.error(f"🌧️ Heavy rainfall: ~{r1h:.2f} in in last hour")
        any_alert = True

    # 24h cumulative alert
    if pd.notna(r24) and r24 >= RAIN_24H_ALERT_IN:
        st.warning(f"🌧️ Significant 24h total: {r24:.2f} in")
        any_alert = True

    # Temperature / humidity alerts (optional)
    if _ensure_col("TemperatureInFahrenheit") and pd.notna(latest["TemperatureInFahrenheit"].iloc[0]):
        temp_f = latest["TemperatureInFahrenheit"].iloc[0]
        if temp_f >= TEMP_ALERT_F:
            st.warning(f"🥵 High temperature: {temp_f:.1f} °F")
            any_alert = True

    if _ensure_col("HumidityInPercentage") and pd.notna(latest["HumidityInPercentage"].iloc[0]):
        hum = latest["HumidityInPercentage"].iloc[0]
        if hum >= HUMIDITY_ALERT_PCT:
            st.info(f"💧 Very high humidity: {hum:.0f}%")
            any_alert = True

    if not any_alert:
        st.success("✅ No active alerts based on current thresholds.")

# ---------- Trends & History ----------
with tab_trend:
    st.subheader("Time‑series")

    left, right = st.columns([3, 2])

    with left:
        if "LevelNum" in fdf and not fdf["LevelNum"].dropna().empty:
            st.markdown("**Water Level (numeric)**")
            st.line_chart(fdf["LevelNum"])
        else:
            st.info("No numeric water‑level data to plot (check `WaterLevel` values).")

        if _ensure_col("PrecipInInches") and not fdf["PrecipInInches"].dropna().empty:
            st.markdown("**Rainfall (per sample)**")
            st.bar_chart(fdf["PrecipInInches"])

    with right:
        if "Rain_1h_in" in fdf and not fdf["Rain_1h_in"].dropna().empty:
            st.markdown("**Rain (rolling 1h)**")
            st.line_chart(fdf["Rain_1h_in"])
        if "Rain_3h_in" in fdf and not fdf["Rain_3h_in"].dropna().empty:
            st.markdown("**Rain (rolling 3h)**")
            st.line_chart(fdf["Rain_3h_in"])
        if "Rain_24h_in" in fdf and not fdf["Rain_24h_in"].dropna().empty:
            st.markdown("**Rain (rolling 24h)**")
            st.line_chart(fdf["Rain_24h_in"])

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if "TemperatureDisplay" in fdf and not fdf["TemperatureDisplay"].dropna().empty:
            st.markdown(f"**Temperature ({temp_unit})**")
            st.line_chart(fdf["TemperatureDisplay"])
    with c2:
        if _ensure_col("HumidityInPercentage") and not fdf["HumidityInPercentage"].dropna().empty:
            st.markdown("**Humidity (%)**")
            st.line_chart(fdf["HumidityInPercentage"])

    st.markdown("---")
    st.markdown("**Latest 100 rows**")
    st.dataframe(fdf.reset_index().sort_values("EntryTime", ascending=False).head(100), use_container_width=True)

# ---------- Map & Meta ----------
with tab_map:
    st.subheader("Sensor location & metadata")
    if HAS_MAP and {"Latitude", "Longitude"}.issubset(df.columns):
        # Use the latest lat/lon if present
        lat = pd.to_numeric(df["Latitude"], errors="coerce").dropna()
        lon = pd.to_numeric(df["Longitude"], errors="coerce").dropna()
        if not lat.empty and not lon.empty:
            m = folium.Map(location=[lat.iloc[0], lon.iloc[0]], zoom_start=14)
            folium.Marker(
                [lat.iloc[0], lon.iloc[0]],
                popup=f"{SITE_NAME}<br>{df['EntryTime'].iloc[0]}",
                icon=folium.Icon(color="blue", icon="info-sign"),
            ).add_to(m)
            st_folium(m, height=400)
        else:
            st.info("No valid latitude/longitude in data.")
    else:
        st.info("Map disabled (install `streamlit_folium` and provide Latitude/Longitude columns).")

    st.markdown("##### Columns detected")
    st.write(list(df.columns))

# ---------- Export ----------
with tab_export:
    st.subheader("Download filtered data")
    out = fdf.reset_index()
    st.download_button(
        "⬇️ Download CSV (filtered)",
        data=out.to_csv(index=False),
        file_name=f"flood_monitor_{SITE_NAME.replace(' ','_')}.csv",
        mime="text/csv",
    )
    st.caption("Tip: Adjust date range and windows in the sidebar, then export.")

st.caption("Source: CSV collected from ESP32 via background worker. Use the ↻ button to refresh.")
