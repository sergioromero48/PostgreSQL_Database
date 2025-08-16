# app.py — Flood Monitoring dashboard (rows CSV + map + weather)
import os, io
from pathlib import Path
from datetime import datetime, timedelta, date

import pandas as pd
import streamlit as st

# Optional libs (map/charts). We degrade gracefully if missing.
HAS_PLOTLY = True
HAS_MAP = True
try:
    import plotly.express as px
except Exception:
    HAS_PLOTLY = False
try:
    import folium
    from streamlit_folium import st_folium
except Exception:
    HAS_MAP = False

# Optional background writer
try:
    from serial_worker import start_worker
except Exception:
    start_worker = None

st.set_page_config(page_title="Flood Monitoring", layout="wide")

# ---------- Config / env ----------
CSV_PATH = Path(os.getenv("CSV_PATH", "data.csv"))
CSV_SCHEMA = os.getenv(
    "CSV_SCHEMA",
    "EntryTime,PrecipInInches,HumidityInPercentage,TemperatureInFahrenheit,WaterLevel",
)
DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "27.7742"))
DEFAULT_LON = float(os.getenv("DEFAULT_LON", "-97.5128"))
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY") or os.getenv("Api_key")

# Alert thresholds
LEVEL_MAP = {"Low": 0, "Nominal": 1, "High": 2, "Unknown": 1}
LEVEL_ALERT_HIGH = 2            # >= High
RAIN_RATE_ALERT_IN_HR = 0.50    # 1h sum
RAIN_24H_ALERT_IN = 2.00        # 24h sum
TEMP_ALERT_F = 95
HUMIDITY_ALERT_PCT = 95

# ---------- Start worker (safe) ----------
if start_worker:
    try:
        start_worker()
        st.caption("Background serial worker running.")
    except Exception as e:
        st.warning(f"Worker failed to start: {e}")

st.title("📡 Flood Monitoring")

# ---------- Sidebar ----------
unit = st.sidebar.radio("Temperature Unit", ["Fahrenheit (°F)", "Celsius (°C)"], index=0)
to_c = (unit == "Celsius (°C)")

now = datetime.now()
default_start = (now - timedelta(days=3)).date()
default_end = (now + timedelta(days=1)).date()
start_date, end_date = st.sidebar.date_input(
    "Date Range", [default_start, default_end],
    min_value=(now.date() - timedelta(days=30)),
    max_value=(now.date() + timedelta(days=30)),
)

st.sidebar.markdown("#### Rain Windows")
w_1h = st.sidebar.number_input("1-hour window (minutes)", 30, 180, 60, 5)
w_3h = st.sidebar.number_input("3-hour window (minutes)", 60, 360, 180, 10)

# ---------- Data load (tolerant of headerless) ----------
def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        if "EntryTime" not in df.columns:
            # headerless fallback
            cols = [c.strip() for c in CSV_SCHEMA.split(",")]
            df = pd.read_csv(path, header=None, names=cols)
        return df
    except Exception:
        # try headerless as last resort
        cols = [c.strip() for c in CSV_SCHEMA.split(",")]
        try:
            return pd.read_csv(path, header=None, names=cols)
        except Exception:
            return pd.DataFrame()

df = load_csv(CSV_PATH)
if df.empty:
    st.info("No data yet… waiting on sensor/worker.")
    st.stop()

# ---------- Normalize ----------
df["EntryTime"] = pd.to_datetime(df["EntryTime"], errors="coerce")
for col in ("PrecipInInches", "HumidityInPercentage", "TemperatureInFahrenheit"):
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
if "WaterLevel" not in df.columns:
    df["WaterLevel"] = "Unknown"
df["LevelNum"] = df["WaterLevel"].map(lambda x: LEVEL_MAP.get(str(x).strip(), 1))

# Optional GPS
has_gps = {"Latitude", "Longitude"}.issubset(df.columns)
if has_gps:
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

# Sort and filter
df = df.sort_values("EntryTime").dropna(subset=["EntryTime"])
mask = (df["EntryTime"].dt.date >= start_date) & (df["EntryTime"].dt.date <= end_date)
fdf = df.loc[mask].copy()
if fdf.empty:
    st.info("No rows in the selected date range.")
    st.stop()

fdf = fdf.set_index("EntryTime")

# Temperature display
def f_to_c(f):
    if pd.isna(f): return None
    return (f - 32) * 5/9

if "TemperatureInFahrenheit" in fdf.columns:
    fdf["TemperatureDisplay"] = fdf["TemperatureInFahrenheit"].apply(f_to_c if to_c else (lambda x: x))
    temp_unit = "°C" if to_c else "°F"
else:
    fdf["TemperatureDisplay"] = None
    temp_unit = "°F" if not to_c else "°C"

# Rolling rainfall
if "PrecipInInches" in fdf.columns:
    fdf["Rain_1h_in"] = fdf["PrecipInInches"].rolling(f"{w_1h}min").sum()
    fdf["Rain_3h_in"] = fdf["PrecipInInches"].rolling(f"{w_3h}min").sum()
    fdf["Rain_24h_in"] = fdf["PrecipInInches"].rolling("1440min").sum()

# ---------- Tabs ----------
tab_rt, tab_trend, tab_map, tab_export = st.tabs(
    ["⚡ Real-time & Alerts", "📈 Trends & History", "🗺️ Map & Weather", "📥 Export"]
)

# ===== Real-time & Alerts =====
with tab_rt:
    st.subheader("Real-time status")
    latest = fdf.tail(1)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        lvl_txt = latest["WaterLevel"].iloc[0] if "WaterLevel" in latest else "—"
        st.metric("Water Level", f"{lvl_txt}")
    with c2:
        r1h = latest["Rain_1h_in"].iloc[0] if "Rain_1h_in" in latest else None
        st.metric("Rain (last 1h)", f"{r1h:.2f} in" if pd.notna(r1h) else "—")
    with c3:
        r24 = latest["Rain_24h_in"].iloc[0] if "Rain_24h_in" in latest else None
        st.metric("Rain (last 24h)", f"{r24:.2f} in" if pd.notna(r24) else "—")
    with c4:
        tdisp = latest["TemperatureDisplay"].iloc[0] if "TemperatureDisplay" in latest else None
        st.metric(f"Air Temp ({temp_unit})", f"{tdisp:.1f}" if pd.notna(tdisp) else "—")

    st.markdown("#### Alerts")
    any_alert = False
    if "LevelNum" in latest and pd.notna(latest["LevelNum"].iloc[0]) and latest["LevelNum"].iloc[0] >= LEVEL_ALERT_HIGH:
        st.error("🚨 Water level **HIGH**")
        any_alert = True
    if r1h is not None and pd.notna(r1h) and r1h >= RAIN_RATE_ALERT_IN_HR:
        st.error(f"🌧️ Heavy rainfall: ~{r1h:.2f} in in last hour")
        any_alert = True
    if r24 is not None and pd.notna(r24) and r24 >= RAIN_24H_ALERT_IN:
        st.warning(f"🌧️ Significant 24h total: {r24:.2f} in")
        any_alert = True
    if "TemperatureInFahrenheit" in latest and pd.notna(latest["TemperatureInFahrenheit"].iloc[0]):
        if latest["TemperatureInFahrenheit"].iloc[0] >= TEMP_ALERT_F:
            st.warning(f"🥵 High temperature: {latest['TemperatureInFahrenheit'].iloc[0]:.1f} °F")
            any_alert = True
    if "HumidityInPercentage" in latest and pd.notna(latest["HumidityInPercentage"].iloc[0]):
        if latest["HumidityInPercentage"].iloc[0] >= HUMIDITY_ALERT_PCT:
            st.info(f"💧 Very high humidity: {latest['HumidityInPercentage'].iloc[0]:.0f}%")
            any_alert = True
    if not any_alert:
        st.success("✅ No active alerts based on current thresholds.")

# ===== Trends & History =====
with tab_trend:
    st.subheader("Time-series")
    left, right = st.columns([3, 2])

    if HAS_PLOTLY:
        with left:
            if "LevelNum" in fdf and not fdf["LevelNum"].dropna().empty:
                st.markdown("**Water Level (numeric)**")
                st.plotly_chart(px.line(fdf.reset_index(), x="EntryTime", y="LevelNum", markers=True), use_container_width=True)
            if "PrecipInInches" in fdf and not fdf["PrecipInInches"].dropna().empty:
                st.markdown("**Rainfall (per sample)**")
                st.plotly_chart(px.bar(fdf.reset_index(), x="EntryTime", y="PrecipInInches"), use_container_width=True)

        with right:
            for col, label in [("Rain_1h_in","Rain (1h)"), ("Rain_3h_in","Rain (3h)"), ("Rain_24h_in","Rain (24h)")]:
                if col in fdf and not fdf[col].dropna().empty:
                    st.markdown(f"**{label}**")
                    st.plotly_chart(px.line(fdf.reset_index(), x="EntryTime", y=col), use_container_width=True)

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            if "TemperatureDisplay" in fdf and not fdf["TemperatureDisplay"].dropna().empty:
                st.markdown(f"**Temperature ({temp_unit})**")
                st.plotly_chart(px.line(fdf.reset_index(), x="EntryTime", y="TemperatureDisplay"), use_container_width=True)
        with c2:
            if "HumidityInPercentage" in fdf and not fdf["HumidityInPercentage"].dropna().empty:
                st.markdown("**Humidity (%)**")
                st.plotly_chart(px.line(fdf.reset_index(), x="EntryTime", y="HumidityInPercentage"), use_container_width=True)
    else:
        st.info("Plotly not installed — install `plotly` for charts.")

    st.markdown("---")
    st.markdown("**Latest 100 rows**")
    st.dataframe(fdf.reset_index().sort_values("EntryTime", ascending=False).head(100), use_container_width=True)

# ===== Map & Weather =====
with tab_map:
    left, right = st.columns([3, 4])
    with left:
        st.subheader("📍 Sensor Map")
        if HAS_MAP:
            if has_gps and not df["Latitude"].dropna().empty and not df["Longitude"].dropna().empty:
                lat = df["Latitude"].dropna().iloc[-1]
                lon = df["Longitude"].dropna().iloc[-1]
            else:
                lat, lon = DEFAULT_LAT, DEFAULT_LON

            m = folium.Map(location=[lat, lon], zoom_start=14)
            folium.Marker([lat, lon],
                          popup=f"Latest point<br>{lat:.5f}, {lon:.5f}",
                          icon=folium.Icon(color="blue", icon="info-sign")).add_to(m)
            st_folium(m, height=420)
        else:
            st.info("Install `folium` and `streamlit-folium` to enable the map.")

    with right:
        st.subheader("🌦️ Current Weather & Forecast")
        to_f = (unit == "Fahrenheit (°F)")
        if not OPENWEATHER_API_KEY:
            st.info("Set OPENWEATHER_API_KEY (or Api_key) to show weather.")
        else:
            import requests
            # choose coords
            if has_gps and not df["Latitude"].dropna().empty and not df["Longitude"].dropna().empty:
                lat = float(df["Latitude"].dropna().iloc[-1]); lon = float(df["Longitude"].dropna().iloc[-1])
            else:
                lat, lon = DEFAULT_LAT, DEFAULT_LON

            # current
            try:
                units = "imperial" if to_f else "metric"
                r = requests.get("https://api.openweathermap.org/data/2.5/weather",
                                 params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": units}, timeout=6)
                if r.status_code == 200:
                    d = r.json()
                    t = d["main"]["temp"]
                    hum = d["main"]["humidity"]
                    wind = d["wind"]["speed"]  # mph if imperial, m/s if metric
                    rain = (d.get("rain", {}).get("1h", 0.0))  # in if imperial, mm if metric
                    if not to_f:  # convert mm->in for display consistency
                        rain = round((rain / 25.4), 2)
                    st.write(f"**Temp:** {t:.1f} {('°F' if to_f else '°C')}  |  **Humidity:** {hum}%  |  **Wind:** {wind} {'mph' if to_f else 'm/s'}  |  **Rain(1h):** {rain} in")
                else:
                    st.warning("OpenWeather current request failed.")
            except Exception as e:
                st.warning(f"Weather error: {e}")

            # forecast (optional mini-chart)
            if HAS_PLOTLY:
                try:
                    units = "imperial" if to_f else "metric"
                    fr = requests.get("https://api.openweathermap.org/data/2.5/forecast",
                                      params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": units},
                                      timeout=6)
                    if fr.status_code == 200:
                        fj = fr.json()
                        times = [x["dt_txt"] for x in fj["list"]]
                        temps = [x["main"]["temp"] for x in fj["list"]]
                        hums = [x["main"]["humidity"] for x in fj["list"]]
                        fdfw = pd.DataFrame({"Time": pd.to_datetime(times), "Temp": temps, "Humidity": hums})
                        st.plotly_chart(px.line(fdfw, x="Time", y=["Temp", "Humidity"], markers=True),
                                        use_container_width=True)
                except Exception:
                    pass

# ===== Export =====
with tab_export:
    st.subheader("Download filtered data")
    out = fdf.reset_index()
    st.download_button(
        "⬇️ Download CSV (filtered)",
        data=out.to_csv(index=False),
        file_name="flood_monitor_filtered.csv",
        mime="text/csv",
    )
    st.caption("Adjust date range/windows in the sidebar, then export.")
