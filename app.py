# app.py
import os, csv
import streamlit as st
from pathlib import Path
from serial_worker import start_worker

# Optional map libs (handled safely)
HAS_MAP = True
try:
    import folium
    from streamlit_folium import st_folium
except Exception:
    HAS_MAP = False

import requests

st.set_page_config(page_title="Flood Monitoring Dashboard", layout="wide")

CSV_PATH = Path(os.getenv("CSV_PATH", "data.csv"))
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY") or os.getenv("Api_key")
DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "27.7742"))
DEFAULT_LON = float(os.getenv("DEFAULT_LON", "-97.5128"))

# Kick off background serial→CSV writer
try:
    start_worker()
    st.success("Background worker started")
except Exception as e:
    st.warning(f"Worker failed to start: {e}")

st.title("📡 Flood Monitoring")
st.write(f"CSV file: `{CSV_PATH}`")

# ---------- Sidebar controls ----------
st.sidebar.subheader("Location & Units")
lat = st.sidebar.number_input("Latitude", value=DEFAULT_LAT, format="%.6f")
lon = st.sidebar.number_input("Longitude", value=DEFAULT_LON, format="%.6f")
unit_choice = st.sidebar.radio("Temperature Unit", ["Fahrenheit (°F)", "Celsius (°C)"], index=0)
use_metric = (unit_choice == "Celsius (°C)")  # metric = °C, m/s

# ---------- Map + Weather section ----------
st.header("🗺️ Map & 🌦️ Weather")

cols = st.columns([1.3, 1.7])

# Map
with cols[0]:
    st.subheader("Map")
    if HAS_MAP:
        try:
            m = folium.Map(location=[lat, lon], zoom_start=13, control_scale=True)
            folium.Marker([lat, lon], popup=f"{lat:.5f}, {lon:.5f}",
                          icon=folium.Icon(color="blue", icon="info-sign")).add_to(m)
            st_folium(m, height=400)
        except Exception as e:
            st.warning(f"Map render error: {e}")
    else:
        st.info("Install `folium` and `streamlit-folium` to enable the interactive map.")

# Weather
with cols[1]:
    st.subheader("Current Weather (OpenWeather)")
    if not OPENWEATHER_API_KEY:
        st.info("Set OPENWEATHER_API_KEY to show current weather.")
    else:
        try:
            units = "metric" if use_metric else "imperial"
            r = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": units},
                timeout=6,
            )
            if r.status_code == 200:
                d = r.json()
                temp = d["main"]["temp"]
                hum = d["main"]["humidity"]
                wind = d["wind"]["speed"]      # m/s in metric, mph in imperial
                rain = d.get("rain", {}).get("1h", 0.0)  # mm in metric, inches in imperial

                # normalize rain to inches for display consistency
                rain_in = (rain / 25.4) if units == "metric" else rain

                c1, c2, c3, c4 = st.columns(4)
                with c1: st.metric("Temp", f"{temp:.1f} {'°C' if use_metric else '°F'}")
                with c2: st.metric("Humidity", f"{hum:.0f}%")
                with c3: st.metric("Wind", f"{wind:.1f} {'m/s' if use_metric else 'mph'}")
                with c4: st.metric("Rain (1h)", f"{rain_in:.2f} in")

                # small details
                st.caption(f"Location: {lat:.5f}, {lon:.5f} • Provider: OpenWeather • Units: {units}")
            else:
                st.warning(f"OpenWeather error {r.status_code}: {r.text[:120]}")
        except Exception as e:
            st.warning(f"Weather request failed: {e}")

# ---------- Your existing CSV viewer ----------
def read_last_rows(path: Path, n: int = 100):
    """Return last n data rows as list[dict]. Works without pandas."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    if not lines:
        return []
    header = [h.strip() for h in lines[0].strip().split(",")]
    rows = []
    for line in lines[1:][-n:]:
        parts = [p.strip() for p in line.strip().split(",")]
        if len(parts) != len(header):
            continue
        rows.append(dict(zip(header, parts)))
    return rows

st.header("📄 Latest Data Rows")
rows = read_last_rows(CSV_PATH, 100)
if not rows:
    st.info("No data yet… waiting on ESP32.")
else:
    # quick HTML table (no pandas needed)
    header = list(rows[0].keys())
    html = ["<div style='max-height:50vh;overflow:auto;border:1px solid #333;border-radius:8px;'>"]
    html += ["<table style='width:100%;border-collapse:collapse;font-size:0.95rem;'>"]
    html += ["<thead><tr>"]
    html += [f"<th style='position:sticky;top:0;background:#111;border-bottom:1px solid #333;padding:6px;text-align:left;'>{h}</th>" for h in header]
    html += ["</tr></thead><tbody>"]
    # show newest first
    for r in reversed(rows[-50:]):
        html += ["<tr>"] + [f"<td style='border-bottom:1px solid #222;padding:6px;'>{r.get(h,'')}</td>" for h in header] + ["</tr>"]
    html += ["</tbody></table></div>"]
    st.markdown("".join(html), unsafe_allow_html=True)

st.caption("Tip: Adjust location in the sidebar. Click the ↻ rerun button (top-right) to refresh.")
