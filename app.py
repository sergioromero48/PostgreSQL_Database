# app.py — ultra-simple CSV rows viewer (no pandas)
import os, io
import streamlit as st
from collections import deque
from pathlib import Path
from serial_worker import start_worker  # starts the background CSV writer

st.set_page_config(page_title="Flood Monitoring (Rows)", layout="wide")

CSV_PATH = Path(os.getenv("CSV_PATH", "data.csv"))
CSV_HAS_HEADER = os.getenv("CSV_HAS_HEADER", "1")  # "1" or "0"
CSV_SCHEMA = os.getenv("CSV_SCHEMA", "EntryTime,PrecipInInches,HumidityInPercentage,TemperatureInFahrenheit,WaterLevel")
MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))  # how many rows to show

# Kick off the serial→CSV writer
try:
    start_worker()
    st.success("Background worker started")
except Exception as e:
    st.warning(f"Worker failed to start: {e}")

st.title("📡 Flood Monitoring — Rows")
st.caption(f"File: {CSV_PATH}")

def tail_lines(path: Path, n: int = 300) -> list[str]:
    """Read last n lines efficiently."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    dq = deque(maxlen=n)
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            dq.append(line.rstrip("\n"))
    return list(dq)

def parse_rows(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """Return (header, rows). If no header, use CSV_SCHEMA env var."""
    if not lines:
        return [], []

    if CSV_HAS_HEADER == "1":
        header = [h.strip() for h in lines[0].split(",")]
        data_lines = lines[1:]
    else:
        header = [h.strip() for h in CSV_SCHEMA.split(",")] if CSV_SCHEMA else []
        data_lines = lines

    rows = []
    for ln in data_lines:
        if not ln.strip():
            continue
        parts = [p.strip() for p in ln.split(",")]
        # pad/trim to header length if needed
        if header:
            if len(parts) < len(header):
                parts += [""] * (len(header) - len(parts))
            elif len(parts) > len(header):
                parts = parts[:len(header)]
        rows.append(parts)
    return header, rows

lines = tail_lines(CSV_PATH, n=MAX_ROWS + 5)
if not lines:
    st.info("No data yet… waiting on ESP32.")
else:
    header, rows = parse_rows(lines)
    if not rows:
        st.info("CSV present but no data rows yet.")
    else:
        st.subheader(f"Last {min(MAX_ROWS, len(rows))} rows (newest first)")
        # newest first
        rows_to_show = list(reversed(rows[-MAX_ROWS:]))

        # render a compact HTML table for speed
        if not header:
            # generate generic headers if still empty
            header = [f"col{i+1}" for i in range(len(rows_to_show[0]))]

        html = io.StringIO()
        html.write('<div style="max-height:70vh;overflow:auto;border:1px solid #444;border-radius:8px;">')
        html.write("<table style='width:100%;border-collapse:collapse;font-size:0.95rem;'>")
        html.write("<thead><tr>")
        for h in header:
            html.write(f"<th style='position:sticky;top:0;background:#111;border-bottom:1px solid #333;padding:6px;text-align:left;'>{h}</th>")
        html.write("</tr></thead><tbody>")
        for r in rows_to_show:
            html.write("<tr>")
            for c in r:
                html.write(f"<td style='border-bottom:1px solid #222;padding:6px;'>{c}</td>")
            html.write("</tr>")
        html.write("</tbody></table></div>")
        st.markdown(html.getvalue(), unsafe_allow_html=True)

        st.download_button(
            "⬇️ Download displayed rows (CSV)",
            data="\n".join([",".join(header)] + [",".join(r) for r in rows_to_show]) if CSV_HAS_HEADER == "1" else
                 "\n".join([",".join(r) for r in rows_to_show]),
            file_name="flood_rows.csv",
            mime="text/csv",
        )

st.caption("Tip: Click the ↻ button (top-right) to refresh.")
