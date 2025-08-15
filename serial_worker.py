"""
serial_worker.py — robust ESP32 → CSV ingester for Flood Monitoring

Background daemon thread that:
  1) Opens the serial port and reads lines
  2) Parses each line into fields (precip, humidity, temp, level, [lat, lon])
  3) Appends a row into CSV used by the Streamlit dashboard

Accepts payload in any of these shapes (examples):
  JSON:
    {"rain_in":0.02,"hum_pct":77,"temp_f":81.3,"level":"High","lat":27.77,"lon":-97.50}
  KV (key=value, commas or spaces):
    rain=0.02 hum=77 tempF=81.3 level=High lat=27.77 lon=-97.50
  CSV (order doesn't matter if header is sent once; otherwise assumes alias order):
    0.02,77,81.3,High,27.77,-97.50

Env vars:
  SERIAL_PORT=/dev/ttyUSB0 (Windows example: COM5)
  BAUDRATE=115200
  CSV_PATH=data.csv
  LOG_EVERY_N=10              # print every N writes
  ALLOW_NEG_RAIN=0            # 1 to allow (else clamp to 0)
  # Optional aliases if your firmware uses different keys
  ALIAS_RAIN=rain_in
  ALIAS_HUM=hum_pct
  ALIAS_TEMP=temp_f
  ALIAS_LEVEL=level
  ALIAS_LAT=lat
  ALIAS_LON=lon
"""

from __future__ import annotations

import os
import csv
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional

try:
    import serial
    from serial.serialutil import SerialException
except Exception as e:
    serial = None
    SerialException = Exception
    print(f"[serial_worker] pyserial not available: {e}")

# ----------------- configuration -----------------
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
BAUDRATE    = int(os.getenv("BAUDRATE", "115200"))
SLEEP_SEC   = 0.10                # small delay between reads
CSV_PATH    = Path(os.getenv("CSV_PATH", "data.csv"))
LOG_EVERY_N = int(os.getenv("LOG_EVERY_N", "10"))

# field aliases (adapt to your firmware keys)
ALIAS_RAIN  = os.getenv("ALIAS_RAIN",  "rain_in")
ALIAS_HUM   = os.getenv("ALIAS_HUM",   "hum_pct")
ALIAS_TEMP  = os.getenv("ALIAS_TEMP",  "temp_f")        # °F preferred by dashboard
ALIAS_LEVEL = os.getenv("ALIAS_LEVEL", "level")
ALIAS_LAT   = os.getenv("ALIAS_LAT",   "lat")
ALIAS_LON   = os.getenv("ALIAS_LON",   "lon")

ALLOW_NEG_RAIN = os.getenv("ALLOW_NEG_RAIN", "0") == "1"

# CSV header used by the dashboard (lat/lon optional)
BASE_HEADERS = [
    "EntryTime",
    "PrecipInInches",
    "HumidityInPercentage",
    "TemperatureInFahrenheit",
    "WaterLevel",
]
GPS_HEADERS = ["Latitude", "Longitude"]
# --------------------------------------------------


def _ensure_csv(has_gps: bool) -> None:
    """Create CSV with header if missing/empty."""
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        headers = BASE_HEADERS + (GPS_HEADERS if has_gps else [])
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(headers)


def _open_serial():
    """Open serial port with simple retries/backoff."""
    if serial is None:
        raise RuntimeError("pyserial not installed. Add `pyserial` to requirements.")
    delay = 1.0
    while True:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
            print(f"[serial_worker] ✅ serial open: {SERIAL_PORT} @ {BAUDRATE}")
            return ser
        except SerialException as e:
            print(f"[serial_worker] ❌ serial open failed: {e} (retry in {delay:.1f}s)")
            time.sleep(delay)
            delay = min(delay * 1.8, 15.0)


# ------------ parsing helpers ------------

# Accept many synonyms from firmware for each field
RAIN_KEYS  = {ALIAS_RAIN, "rain", "rain_in", "precip_in", "precip", "p_in"}
HUM_KEYS   = {ALIAS_HUM, "hum", "humidity", "hum_pct", "humid_pct"}
TEMP_KEYS  = {ALIAS_TEMP, "temp", "temp_f", "temperature_f", "t_f"}
LEVEL_KEYS = {ALIAS_LEVEL, "lvl", "level", "water_level", "stage"}
LAT_KEYS   = {ALIAS_LAT, "lat", "latitude"}
LON_KEYS   = {ALIAS_LON, "lon", "lng", "longitude"}

# For CSV payload lines with fixed order (fallback)
CSV_GUESS_ORDER = [RAIN_KEYS, HUM_KEYS, TEMP_KEYS, LEVEL_KEYS, LAT_KEYS, LON_KEYS]


def _to_float(x) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


def _clamp(val: Optional[float], lo: float, hi: float) -> Optional[float]:
    if val is None:
        return None
    return max(lo, min(hi, val))


def _normalize(parsed: Dict[str, str]) -> Tuple[Optional[float], Optional[float], Optional[float], str, Optional[float], Optional[float]]:
    """Map parsed dict to (rain_in, hum_pct, temp_f, level, lat, lon) with sanity checks."""
    def pick(keys):
        for k in keys:
            if k in parsed and parsed[k] not in ("", None):
                return parsed[k]
        return None

    rain = _to_float(pick(RAIN_KEYS))
    hum  = _to_float(pick(HUM_KEYS))
    temp = _to_float(pick(TEMP_KEYS))
    lvl  = pick(LEVEL_KEYS)
    lat  = _to_float(pick(LAT_KEYS))
    lon  = _to_float(pick(LON_KEYS))

    # sanity
    if rain is not None:
        if not ALLOW_NEG_RAIN:
            rain = max(0.0, rain)
        # reasonably large single-sample clamp (adjust if your payload is hourly totals)
        rain = _clamp(rain, 0.0, 20.0)

    if hum is not None:
        hum = _clamp(hum, 0.0, 100.0)

    # temp is °F in dashboard; if your firmware sends °C, convert in firmware or here.
    # Heuristic: if temp looks like °C (very low), convert; else trust as °F.
    if temp is not None:
        if temp < -40 or temp > 170:
            temp = None  # absurd value, drop
        elif -40 <= temp <= 60:  # likely °C
            temp = temp * 9/5 + 32

    if not lvl:
        # try to infer from numeric codes if sent (0/1/2)
        # 0=Low, 1=Nominal, 2=High
        code = _to_float(pick({"lvl_code", "level_code", "lvl"}))
        if code is not None:
            lvl = "High" if code >= 2 else ("Nominal" if code >= 1 else "Low")
        else:
            lvl = "Unknown"

    return rain, hum, temp, str(lvl), lat, lon


def _parse_line(line: str) -> Tuple[Optional[float], Optional[float], Optional[float], str, Optional[float], Optional[float], bool]:
    """
    Returns (rain_in, hum_pct, temp_f, level, lat, lon, has_gps).
    Supports JSON, key=value, or simple CSV (with known order).
    """
    s = line.strip()
    if not s:
        return None, None, None, "Unknown", None, None, False

    # 1) JSON
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            rain, hum, temp, lvl, lat, lon = _normalize({str(k).strip(): obj[k] for k in obj})
            return rain, hum, temp, lvl, lat, lon, (lat is not None and lon is not None)
        except Exception:
            # fall through
            pass

    # 2) key=value (comma or space separated)
    if "=" in s:
        # split by commas or spaces
        parts = [p for chunk in s.replace(",", " ").split() if (p := chunk.strip())]
        kv = {}
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                kv[k.strip()] = v.strip()
        if kv:
            rain, hum, temp, lvl, lat, lon = _normalize(kv)
            return rain, hum, temp, lvl, lat, lon, (lat is not None and lon is not None)

    # 3) bare CSV numbers/strings
    # try to map by a guessed order
    if "," in s:
        vals = [v.strip() for v in s.split(",")]
        parsed = {}
        for i, v in enumerate(vals):
            if i >= len(CSV_GUESS_ORDER):
                break
            for k in CSV_GUESS_ORDER[i]:
                parsed[next(iter(k)) if isinstance(k, set) else k] = v
        rain, hum, temp, lvl, lat, lon = _normalize(parsed)
        return rain, hum, temp, lvl, lat, lon, (lat is not None and lon is not None)

    # otherwise treat entire line as level text
    return None, None, None, s, None, None, False


# ------------- read loop & writer -------------

_stop_event = threading.Event()
_thread: Optional[threading.Thread] = None


def _read_loop():
    # open once outside; on error re-open
    ser = _open_serial()
    last_signature = None  # deduplicate identical rows
    write_count = 0
    has_gps_once = False

    # ensure at least base CSV
    _ensure_csv(has_gps=False)

    while not _stop_event.is_set():
        try:
            raw = ser.readline().decode(errors="ignore").strip()
            if not raw:
                time.sleep(SLEEP_SEC)
                continue

            rain, hum, temp, lvl, lat, lon, has_gps = _parse_line(raw)

            # if GPS appears for the first time, upgrade the CSV header if needed
            if has_gps and not has_gps_once:
                has_gps_once = True
                # If file exists with base header, we won't rewrite old rows; we only ensure future rows carry GPS columns.
                _ensure_csv(has_gps=True)

            # Create signature to avoid duplicating an identical line repeatedly
            sig = (round(rain or -1, 4), round(hum or -1, 2), round(temp or -999, 2), lvl, round(lat or 0, 6), round(lon or 0, 6))
            if sig == last_signature:
                continue
            last_signature = sig

            row = [
                datetime.now().isoformat(timespec="seconds"),
                f"{rain:.4f}" if rain is not None else "",
                f"{hum:.1f}" if hum is not None else "",
                f"{temp:.2f}" if temp is not None else "",
                lvl,
            ]

            if has_gps_once:
                row += [
                    f"{lat:.6f}" if lat is not None else "",
                    f"{lon:.6f}" if lon is not None else "",
                ]

            with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)

            write_count += 1
            if write_count % max(1, LOG_EVERY_N) == 0:
                print(f"[serial_worker] wrote {write_count} rows (latest: {row})")

        except KeyboardInterrupt:
            break
        except SerialException as e:
            print(f"[serial_worker] ⚠️ serial error: {e} (reopening...)")
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(1.0)
            ser = _open_serial()
        except Exception as e:
            print(f"[serial_worker] ⚠️ loop error: {e}")
            time.sleep(0.25)

    try:
        ser.close()
    except Exception:
        pass
    print("[serial_worker] stopped.")


def start_worker() -> threading.Thread:
    """Start the background reader if not already running; returns the thread."""
    global _thread
    if _thread and _thread.is_alive():
        return _thread
    _stop_event.clear()
    _thread = threading.Thread(target=_read_loop, daemon=True)
    _thread.start()
    return _thread


def stop_worker(timeout: float = 2.0) -> None:
    """Signal the worker to stop and wait a bit."""
    _stop_event.set()
    t = _thread
    if t:
        t.join(timeout=timeout)
