# app.py — plots for CSV: EntryTimeUTC,Latitude,Longitude,Temperature,Humidity,Light,Precipitation,WaterLevel
import os, csv
import streamlit as st
from pathlib import Path
from serial_worker import start_worker
from plotly.subplots import make_subplots


# Optional map libs (handled safely)
HAS_MAP = True
try:
    import folium
    from streamlit_folium import st_folium
except Exception:
    HAS_MAP = False

import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="Flood Monitoring Dashboard", layout="wide")

CSV_PATH = Path(os.getenv("CSV_PATH", "data.csv"))
OPENWEATHER_API_KEY = (os.getenv("OPENWEATHER_API_KEY") or os.getenv("Api_key") or "").strip()
DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "27.7742"))
DEFAULT_LON = float(os.getenv("DEFAULT_LON", "-97.5128"))

# ---- Start background worker (only once) ----
if "worker_started" not in st.session_state:
    try:
        st.session_state.worker_started = start_worker()
        st.success("Background worker started")
    except Exception as e:
        st.warning(f"Worker failed to start: {e}")
else:
    st.caption("Background worker already running.")

st.title("📡 Flood Monitoring")
st.write(f"CSV file: `{CSV_PATH}`")

# ---------- Sidebar controls ----------
st.sidebar.subheader("Location & Units")
lat = st.sidebar.number_input("Latitude", value=DEFAULT_LAT, format="%.6f")
lon = st.sidebar.number_input("Longitude", value=DEFAULT_LON, format="%.6f")

# Display unit for plots/metrics from our CSV
unit_choice = st.sidebar.radio("Display Temperature As", ["Celsius (°C)", "Fahrenheit (°F)"], index=0)
disp_metric_c = (unit_choice == "Celsius (°C)")

# What unit does your CSV Temperature come in?
src_unit_choice = st.sidebar.radio("CSV Temperature Source Unit", ["Celsius (°C)", "Fahrenheit (°F)"], index=0)
src_is_c = (src_unit_choice == "Celsius (°C)")

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

# Weather (current only)
with cols[1]:
    st.subheader("Current Weather (OpenWeather)")
    if not OPENWEATHER_API_KEY:
        st.info("Set OPENWEATHER_API_KEY to show current weather.")
    else:
        try:
            units = "metric" if disp_metric_c else "imperial"
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

                rain_in = (rain / 25.4) if units == "metric" else rain

                c1, c2, c3, c4 = st.columns(4)
                with c1: st.metric("Temp", f"{temp:.1f} {'°C' if disp_metric_c else '°F'}")
                with c2: st.metric("Humidity", f"{hum:.0f}%")
                with c3: st.metric("Wind", f"{wind:.1f} {'m/s' if disp_metric_c else 'mph'}")
                with c4: st.metric("Rain (1h)", f"{rain_in:.2f} in")
                st.caption(f"Location: {lat:.5f}, {lon:.5f} • Provider: OpenWeather • Units: {units}")
            else:
                st.warning(f"OpenWeather error {r.status_code}: {r.text[:120]}")
        except Exception as e:
            st.warning(f"Weather request failed: {e}")

# ---------- Helpers for CSV parsing (no pandas) ----------
COLS_EXPECTED = [
    "EntryTimeUTC","Latitude","Longitude","Temperature","Humidity","Light","Precipitation","WaterLevel"
]

def to_celsius(val, src_is_c):
    if val is None:
        return None
    return val if src_is_c else (val - 32.0) * 5.0/9.0


def _to_float(x):
    try:
        return float(x)
    except Exception:
        return None

def _parse_time_utc(s):
    s = (s or "").strip()
    # handle "YYYY-MM-DDTHH:MM:SSZ" or without Z
    if s.endswith("Z"):
        s = s[:-1]
    try:
        return datetime.fromisoformat(s)
    except Exception:
        # also accept space as separator
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                pass
    return None

def read_rows(path: Path, n: int | None = None):
    """Read all (or last n) rows into dicts with normalized types."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    if not lines:
        return []
    header = [h.strip() for h in lines[0].strip().split(",")]
    # Normalize header aliases (case-insensitive) for precipitation so downstream logic works
    precip_aliases = {"precip", "rain", "rainfall", "precipitation (in)", "precip_in", "rain_in"}
    # Build a mapping of original header name -> canonical name
    canon_map = {}
    for h in header:
        key_l = h.lower()
        if key_l in precip_aliases:
            canon_map[h] = "Precipitation"
        else:
            canon_map[h] = h  # unchanged

    data_lines = lines[1:] if len(lines) > 1 else []
    if n is not None:
        data_lines = data_lines[-n:]

    out = []
    for line in data_lines:
        parts = [p.strip() for p in line.strip().split(",")]
        if len(parts) != len(header):
            continue
        row_raw = dict(zip(header, parts))
        # Apply canonical key names
        row = {}
        for k, v in row_raw.items():
            row[canon_map.get(k, k)] = v
        # Normalize names if header exactly matches expected
        # (If not, we still try to use the provided names.)
        ts_key = "EntryTimeUTC" if "EntryTimeUTC" in row else "EntryTime"
        row["_time"] = _parse_time_utc(row.get(ts_key, ""))

        # floats
        for k in ("Latitude","Longitude","Temperature","Humidity","Light"):
            if k in row:
                row[k] = _to_float(row[k])
        # Precipitation handling: treat blank/empty as 0 (common meaning = no rain) but keep None if truly missing
        if "Precipitation" in row:
            val = row["Precipitation"].strip()
            if val == "":
                row["Precipitation"] = 0.0
            else:
                row["Precipitation"] = _to_float(val)
        out.append(row)

    out = [r for r in out if r["_time"] is not None]
    out.sort(key=lambda r: r["_time"])
    return out

# ---------- Live metrics from CSV ----------
rows_all = read_rows(CSV_PATH, None)
st.header("📊 Plots")
if not rows_all:
    st.info("No CSV rows yet — plots will appear when data arrives.")
else:
    latest = rows_all[-1]
    # Temperature conversion for display
    def to_disp_temp(val):
        if val is None:
            return None
        if src_is_c and disp_metric_c:
            return val
        if src_is_c and not disp_metric_c:
            return (val * 9/5) + 32
        if not src_is_c and disp_metric_c:
            return (val - 32) * 5/9
        return val

    # Top metrics
    # Top metrics (always show current sensor Temp in °C and Humidity in %)
    m0, m1, m2, m3 = st.columns(4)

    tc = to_celsius(latest.get("Temperature"), src_is_c)
    hc = latest.get("Humidity")
    lv = latest.get("Light")
    pv = latest.get("Precipitation")
    wl = latest.get("WaterLevel", "")

    with m0:
        st.metric("Sensor Temp (°C)", f"{tc:.1f} °C" if tc is not None else "—")
    with m1:
        st.metric("Sensor Humidity (%)", f"{hc:.1f} %" if hc is not None else "—")
    with m2:
        st.metric("Light", f"{lv:.0f}" if lv is not None else "—")
    with m3:
        st.metric("Water Level", wl if wl else "—")


    # Prepare series (last N)
    N = st.slider("Samples to show", min_value=10, max_value=1000, value=200, step=10)
    sample = rows_all[-N:]
    xs = [r["_time"] for r in sample]

    temps_disp = [to_disp_temp(r.get("Temperature")) for r in sample]
    hums       = [r.get("Humidity") for r in sample]
    lights     = [r.get("Light") for r in sample]
    precips    = [r.get("Precipitation") for r in sample]
    levels     = [r.get("WaterLevel","") for r in sample]

    # Temperature & Humidity
    fig_th = make_subplots(specs=[[{"secondary_y": True}]])
    if any(t is not None for t in temps_disp):
        fig_th.add_trace(
            go.Scatter(x=xs, y=temps_disp, mode="lines+markers",
                    name=f"Temp ({'°C' if disp_metric_c else '°F'})"),
            secondary_y=False
        )
    if any(h is not None for h in hums):
        fig_th.add_trace(
            go.Scatter(x=xs, y=hums, mode="lines+markers", name="Humidity (%)"),
            secondary_y=True
        )

    fig_th.update_yaxes(title_text=f"Temp ({'°C' if disp_metric_c else '°F'})", secondary_y=False)
    fig_th.update_yaxes(title_text="Humidity (%)", secondary_y=True, rangemode="tozero")
    fig_th.update_layout(margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_th, use_container_width=True)


    # Light
    if any(l is not None for l in lights):
        fig_l = go.Figure()
        fig_l.add_scatter(x=xs, y=lights, mode="lines+markers", name="Light")
        fig_l.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title="arb. units")
        st.plotly_chart(fig_l, use_container_width=True)

    # Precipitation (inches, per-sample)
    if any(p is not None for p in precips):
        fig_p = go.Figure()
        fig_p.add_scatter(x=xs, y=precips, mode="lines+markers", name="Precipitation (in)")
        fig_p.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title="inches")
        st.plotly_chart(fig_p, use_container_width=True)

    # Water Level (categorical → colored markers)
    if any(levels):
        level_map = {"Low":0, "Nominal":1, "High":2, "Unknown":-1}
        y_level = [level_map.get(l, None) for l in levels]
        fig_w = go.Figure()
        fig_w.add_scatter(
            x=xs, y=y_level, mode="markers+lines", name="Water Level",
            text=levels, hovertemplate="%{x|%Y-%m-%d %H:%M:%S} — %{text}<extra></extra>"
        )
        fig_w.update_yaxes(
            tickmode="array",
            tickvals=[-1,0,1,2],
            ticktext=["Unknown","Low","Nominal","High"],
            range=[-1.5, 2.5]
        )
        fig_w.update_layout(margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_w, use_container_width=True)

# ---------- Latest Data Rows (table) ----------
st.header("📄 Latest Data Rows")
def read_last_rows(path: Path, n: int = 200):
    rows = read_rows(path, n)
    return rows

rows = read_last_rows(CSV_PATH, 200)
if not rows:
    st.info("No data yet… waiting on ESP32.")
else:
    # Derive header from the union of keys in the latest row (preserve expected order when present)
    preferred = ["EntryTimeUTC","Latitude","Longitude","Temperature","Humidity","Light","Precipitation","WaterLevel"]
    keys = list({k for r in rows for k in r.keys() if not k.startswith("_")})
    header = [k for k in preferred if k in keys] + [k for k in keys if k not in preferred]

    html = ["<div style='max-height:50vh;overflow:auto;border:1px solid #333;border-radius:8px;'>"]
    html += ["<table style='width:100%;border-collapse:collapse;font-size:0.95rem;'>"]
    html += ["<thead><tr>"]
    html += [f"<th style='position:sticky;top:0;background:#111;border-bottom:1px solid #333;padding:6px;text-align:left;'>{h}</th>" for h in header]
    html += ["</tr></thead><tbody>"]
    # newest first
    for r in reversed(rows[-100:]):
        html += ["<tr>"]
        for h in header:
            if h == "EntryTimeUTC" and "_time" in r and r["_time"]:
                v = r["_time"].isoformat(sep=" ", timespec="seconds") + " UTC"
            else:
                v = r.get(h, "")
                if isinstance(v, float):
                    v = f"{v:.3f}"
            html += [f"<td style='border-bottom:1px solid #222;padding:6px;'>{v}</td>"]
        html += ["</tr>"]
    html += ["</tbody></table></div>"]
    st.markdown("".join(html), unsafe_allow_html=True)

st.caption("Tip: change unit settings in the sidebar. Click the ↻ rerun button (top-right) to refresh.")
