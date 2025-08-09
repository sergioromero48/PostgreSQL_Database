# app.py
import os, csv
import streamlit as st
from pathlib import Path
from serial_worker import start_worker

st.set_page_config(page_title="Flood Monitoring Dashboard", layout="wide")

CSV_PATH = Path(os.getenv("CSV_PATH", "data.csv"))

# Kick off background serial→CSV writer
try:
    start_worker()
    st.success("Background worker started")
except Exception as e:
    st.warning(f"Worker failed to start: {e}")

st.title("📡 Flood Monitoring")
st.write(f"CSV file: `{CSV_PATH}`")

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

rows = read_last_rows(CSV_PATH, 100)
if not rows:
    st.info("No data yet… waiting on ESP32.")
else:
    # quick HTML table (no pandas needed)
    header = list(rows[0].keys())
    html = ["<table><thead><tr>"]
    html += [f"<th>{h}</th>" for h in header]
    html += ["</tr></thead><tbody>"]
    # show newest first
    for r in reversed(rows[-50:]):
        html += ["<tr>"] + [f"<td>{r.get(h,'')}</td>" for h in header] + ["</tr>"]
    html += ["</tbody></table>"]
    st.markdown("".join(html), unsafe_allow_html=True)

st.caption("Tip: Click the ↻ rerun button in the top-right to refresh.")

