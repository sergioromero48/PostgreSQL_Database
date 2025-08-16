"""
Background thread that:
1. Opens the ESP32 serial port
2. Parses each line into (precip, humidity, temp, level)
3. Inserts the row into Postgres

Import and call start_worker() once from app.py.
""" 
# serial_worker.py
import os, threading, time, serial, csv
from datetime import datetime
from pathlib import Path

# ----------------- configuration -----------------
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
BAUDRATE    = int(os.getenv("BAUDRATE", "115200"))
SLEEP_SEC   = 2
CSV_PATH    = Path(os.getenv("CSV_PATH", "data.csv"))
# --------------------------------------------------

def _parse_line(line: str):
    """
    Adapt this to your firmware payload.
    Currently: returns (precip_in, humidity_str, temp_F_or_None, water_level_txt)
    """
    # TODO: change this to your real format if different
    precip = None
    humidity = None
    temp = None
    level = line.strip() or "Unknown"
    return precip, humidity, temp, level

def _ensure_csv():
    if not CSV_PATH.exists():
        with CSV_PATH.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["EntryTime","PrecipInInches","HumidityInPercentage",
                        "TemperatureInFahrenheit","WaterLevel"])

def _read_loop():
    _ensure_csv()

    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        print(f"✅ Serial open: {SERIAL_PORT}")
    except Exception as e:
        print(f"❌ Serial open failed for {SERIAL_PORT}: {e}")
        return

    while True:
        try:
            raw = ser.readline().decode(errors="ignore").strip()
            if not raw:
                time.sleep(SLEEP_SEC)
                continue

            p, h, t, lvl = _parse_line(raw)

            # append a row
            with CSV_PATH.open("a", newline="") as f:
                w = csv.writer(f)
                w.writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    p, h, t, lvl
                ])

            print(f"➕ wrote row: {p}, {h}, {t}, {lvl}")
            time.sleep(SLEEP_SEC)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"⚠️ serial loop error: {e}")
            time.sleep(SLEEP_SEC)

def start_worker():
    t = threading.Thread(target=_read_loop, daemon=True)
    t.start()

