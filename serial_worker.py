# serial_worker.py — ESP32 → CSV (raw rows by default)
import os, threading, time, serial
from datetime import datetime
from pathlib import Path

SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
BAUDRATE    = int(os.getenv("BAUDRATE", "115200"))
SLEEP_SEC   = float(os.getenv("SLEEP_SEC", "0.1"))

CSV_PATH       = Path(os.getenv("CSV_PATH", "data.csv"))
CSV_HAS_HEADER = os.getenv("CSV_HAS_HEADER", "1")   # "1" writes header once, "0" never
CSV_SCHEMA     = os.getenv("CSV_SCHEMA", "EntryTime,PrecipInInches,HumidityInPercentage,TemperatureInFahrenheit,WaterLevel")
CSV_MODE       = os.getenv("CSV_MODE", "raw")       # "raw" or "structured"

# ------------- Structured (optional) parsing helpers -------------
def _structured_parse(line: str):
    """
    Convert a firmware line into fields in the same order as CSV_SCHEMA.
    Examples accepted: JSON, key=value, or plain CSV.
    Return a list[str] (without timestamp).
    """
    s = line.strip()
    if not s:
        return []

    # simplest: if already CSV values (no keys), just split
    if "," in s and "=" not in s and not s.startswith("{"):
        return [p.strip() for p in s.split(",")]

    # key=value fallback
    if "=" in s:
        # map common keys to expected order
        kv = {}
        for chunk in s.replace(",", " ").split():
            if "=" in chunk:
                k, v = chunk.split("=", 1)
                kv[k.strip().lower()] = v.strip()
        # Build in the CSV_SCHEMA order (minus EntryTime)
        cols = [c.strip() for c in CSV_SCHEMA.split(",")]
        value_cols = [c for c in cols if c.lower() != "entrytime"]
        out = []
        for col in value_cols:
            key = col.lower()
            # try exact; else some common aliases
            aliases = {
                "precipininches": ("rain", "rain_in", "precip", "precip_in"),
                "humidityinpercentage": ("hum", "humidity", "hum_pct"),
                "temperatureinfahrenheit": ("temp_f", "temp", "temperature", "t_f"),
                "waterlevel": ("level", "lvl", "stage"),
            }.get(key, ())
            val = kv.get(key)
            if val is None:
                for a in aliases:
                    if a in kv:
                        val = kv[a]; break
            out.append("" if val is None else val)
        return out

    # JSON optional (minimal)
    if s.startswith("{") and s.endswith("}"):
        try:
            import json
            obj = json.loads(s)
            cols = [c.strip() for c in CSV_SCHEMA.split(",")]
            value_cols = [c for c in cols if c.lower() != "entrytime"]
            return [str(obj.get(c, "")) for c in value_cols]
        except Exception:
            return []

    # fallback: treat as a single field
    return [s]

def _ensure_header_if_needed():
    if CSV_HAS_HEADER == "1":
        if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
            with CSV_PATH.open("w", encoding="utf-8") as f:
                f.write(CSV_SCHEMA.strip() + "\n")

def _append_row(values: list[str]):
    with CSV_PATH.open("a", encoding="utf-8") as f:
        f.write(",".join(values) + "\n")

def _read_loop():
    _ensure_header_if_needed()

    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        print(f"[worker] serial open: {SERIAL_PORT} @ {BAUDRATE}")
    except Exception as e:
        print(f"[worker] serial open failed: {e}")
        return

    while True:
        try:
            raw = ser.readline().decode(errors="ignore").strip()
            if not raw:
                time.sleep(SLEEP_SEC)
                continue

            ts = datetime.now().isoformat(timespec="seconds")

            if CSV_MODE == "raw":
                # RAW MODE: prepend timestamp, then the line as-is
                if CSV_HAS_HEADER == "1" and (not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0):
                    _ensure_header_if_needed()
                _append_row([ts] + [v.strip() for v in raw.split(",")])
            else:
                # STRUCTURED MODE: parse into schema order (minus EntryTime)
                fields = _structured_parse(raw)
                _append_row([ts] + fields)

            # tiny breather
            time.sleep(SLEEP_SEC)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[worker] loop error: {e}")
            time.sleep(0.25)

def start_worker():
    t = threading.Thread(target=_read_loop, daemon=True)
    t.start()
    return t
