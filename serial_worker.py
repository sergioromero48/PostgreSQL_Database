"""
Background thread that:
1. Opens the ESP32 serial port
2. Parses each line into (precip, humidity, temp, level)
3. Inserts the row into Postgres

Import and call start_worker() once from app.py.
"""
import os, threading, time, serial, psycopg2
from database import get_conn

# ----------------- configuration -----------------
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")  # Jetson Nano UART
BAUDRATE    = int(os.getenv("BAUDRATE", "115200"))
SLEEP_SEC   = 2
# --------------------------------------------------

def _parse_line(line: str):
    """
    ESP32 sends 7-char string like '50xxxx' (see original code) –
    adapt this if your firmware changes.
    Returns: (precip_in, humidity_pct, temp_F, water_level_txt)
    """
    precip = int(line[2:4]) / 10          # inches
    humidity = f"{int(line[5:7]) / 10}%"  # 'nn.n%'
    temp = None                           # ESP line had no temp; fill later
    level_code = line[1]
    level = {"0": "Low", "1": "Nominal", "2": "High"}.get(level_code, "Unknown")
    return precip, humidity, temp, level

def _read_loop():
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
    conn = get_conn()
    cur  = conn.cursor()
    while True:
        raw = ser.readline().decode(errors="ignore").strip()
        if not raw:
            time.sleep(SLEEP_SEC)
            continue
        try:
            p, h, t, lvl = _parse_line(raw)
            cur.execute(
                """INSERT INTO weatherDataFromSite1
                   (PrecipInInches, HumidityInPercentage,
                    TemperatureInFahrenheit, WaterLevel)
                   VALUES (%s,%s,%s,%s)""",
                (p, h, t, lvl)
            )
            conn.commit()
        except Exception as e:
            print("!!! insert failed:", e)
        time.sleep(SLEEP_SEC)

def start_worker():
    t = threading.Thread(target=_read_loop, daemon=True)
    t.start()
