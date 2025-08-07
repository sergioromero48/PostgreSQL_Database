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
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        print(f"Successfully opened serial port: {SERIAL_PORT}")
    except Exception as e:
        print(f"Failed to open serial port {SERIAL_PORT}: {e}")
        print("Serial worker will not read data, but app will continue...")
        return
    
    try:
        conn = get_conn()
        cur  = conn.cursor()
        print("Database connection established")
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        ser.close()
        return
    
    while True:
        try:
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
                print(f"Inserted data: {p}, {h}, {t}, {lvl}")
            except Exception as e:
                print("!!! insert failed:", e)
            time.sleep(SLEEP_SEC)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Serial read error: {e}")
            time.sleep(SLEEP_SEC)
    
    try:
        ser.close()
        conn.close()
    except:
        pass

def start_worker():
    t = threading.Thread(target=_read_loop, daemon=True)
    t.start()
