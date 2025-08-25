# Flood Monitoring Dashboard

Real-time sensor dashboard (Streamlit + Plotly) that ingests serial data from an MCU (e.g. ESP32) and stores every reading to a CSV file for plotting (Temperature, Humidity, Light, Precipitation, Water Level). Optional live weather overlay via OpenWeather and map via Folium.

---
> ⚠️ Windows notes: The Windows / TCP bridge workflow has not been fully end-to-end tested yet. Core logic is cross-platform, but direct COM passthrough limitations in Docker Desktop mean you should treat the Windows instructions as experimental. Prefer running inside WSL or (recommended) run the app **without Docker** on Windows and let it access the serial port directly. Report any issues you encounter.

## 1. Features
- Auto‑starting background worker (`serial_worker.py`) that reads serial or a TCP serial bridge.
- CSV logging with durable flush after each line.
- Interactive Streamlit UI: metrics, plots (Temp/Humidity dual axis, Light, Precipitation, Water Level state), table of latest rows, map + current weather.
- Temperature unit conversion (C/F) independent of source unit.
- Cross‑platform serial support:
  - Linux / WSL: direct `/dev/tty*` or `/dev/ttyUSB*` access.
  - Windows: AUTO scan or TCP bridge (`SERIAL_TCP`), optional WSL device mapping.
  - AUTO port scanning if you don't specify a port.
- Header alias normalization for precipitation (rain/precip/rainfall → Precipitation).

---
## 2. Repository Layout
```
app.py                # Streamlit UI
serial_worker.py      # Background serial (or TCP) reader → CSV
run.sh                # Linux/WSL Docker build+run helper
run_windows.ps1       # Windows / PowerShell build+run helper (serial strategies included)
Dockerfile            # Container image (Python 3.10 slim)
requirements.txt      # Python deps
scripts/
  setup_docker_linux.sh      # Simple apt-based Docker install
  setup_docker_windows.ps1   # Docker Desktop install helper
README.md             # This file
data/                 # CSV output directory (bind mounted when using Docker)
```

---
## 3. Data Format
CSV columns (default schema):
```
EntryTimeUTC,Latitude,Longitude,Temperature,Humidity,Light,Precipitation,WaterLevel
```
- `EntryTimeUTC` added by worker (UTC ISO).
- `WaterLevel` can be numeric (0/1/2) or tokens (Low/Nominal/High/Unknown).
- Blank precipitation values become `0.0` so charts display a zero line.

MCU sends lines in either form (prefix optional if DATA_PREFIX matches `DATA,`):
```
DATA,<tempC>,<humidity>,<light>,<precip>,<level>
<tempC>,<humidity>,<light>,<precip>,<level>
```
Example:
```
DATA,24.7,51.2,22340,0,Nominal
```

---
## 4. Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `SERIAL_PORT` | Serial device (or AUTO) | `AUTO` |
| `SERIAL_TCP`  | `host:port` for TCP bridge (overrides device) | (unset) |
| `BAUDRATE` | Serial baud | `115200` |
| `CSV_PATH` | Path to CSV inside container / host | `/app/data/data.csv` (via run scripts) |
| `CSV_SCHEMA` | Column header list | See above |
| `DATA_PREFIX` | Optional line prefix to strip | `DATA,` |
| `OPENWEATHER_API_KEY` | OpenWeather API key | (unset) |
| `DEFAULT_LAT` / `DEFAULT_LON` | Location stored in CSV & used for weather/map | Provided in run scripts |
| `PRINT_EVERY_WRITE` | Log each accepted line | `1` |
| `SLEEP_SEC` | Idle loop sleep when no serial line | `0.02` |

---
## 5. Quick Start (Docker) – Linux / WSL
1. (Optional) Install Docker: `sudo bash scripts/setup_docker_linux.sh`
2. Plug in your MCU (e.g. appears as `/dev/ttyUSB0`).
3. Run:
   ```bash
   sudo ./run.sh
   ```
   (If your user is in the `docker` group you can omit `sudo`.)
4. Open: http://localhost:8501
5. Stop container: `docker rm -f floodDash`

`run.sh` will:
- Build image `flood-monitoring`.
- Mount `./data` to `/app/data`.
- Pass through chosen serial device (`SERIAL=/dev/ttyUSB0` by default).
- Set environment variables (API key placeholders built-in; replace as needed).

To override device:
```bash
SERIAL=/dev/ttyUSB1 ./run.sh
```

To change port:
```bash
PORT=9000 ./run.sh
```

---
## 6. Quick Start (Docker) – Windows (PowerShell)
1. Install Docker Desktop (see `scripts/setup_docker_windows.ps1` if desired).
2. Decide serial strategy:
   - WSL method: run this inside WSL; set `SERIAL=/dev/ttyS4` (or whichever WSL presents) – mapping will work.
   - TCP bridge (native Windows): expose your COM port over TCP and use `SERIAL_TCP`.
3. Build & run:
   ```powershell
   ./run_windows.ps1
   ```
4. With explicit COM (inside WSL):
   ```powershell
   $env:SERIAL="/dev/ttyS4"; ./run_windows.ps1
   ```
5. With TCP bridge (native Windows):
   ```powershell
   $env:SERIAL_TCP="localhost:7777"; ./run_windows.ps1
   ```
6. Browse http://localhost:8501

### TCP Bridge Example
In WSL (or another host) forward a real serial device:
```bash
socat -d -d TCP-LISTEN:7777,fork FILE:/dev/ttyUSB0,b115200,raw,echo=0
```
Then set `SERIAL_TCP=localhost:7777` before launching the container.

---
## 7. Running Without Docker (Local Python)
1. Python 3.10+ and system `libpq-dev` etc. (if you later add Postgres) – for current CSV mode, minimal libs suffice.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Export env vars (example):
   ```bash
   export SERIAL_PORT=/dev/ttyUSB0
   export OPENWEATHER_API_KEY=YOUR_KEY
   export DEFAULT_LAT=29.58145
   export DEFAULT_LON=-98.616441
   ```
4. Run Streamlit:
   ```bash
   streamlit run app.py --server.port=8501 --server.address=0.0.0.0
   ```

The worker starts once per session automatically when the app imports `start_worker()`.

---
## 8. Verification / Diagnostics
- Worker log lines (`[worker] wrote:`) appear in container or Streamlit server stdout.
- To ensure data is flowing: open `data/data.csv` while MCU sends lines; file should grow.
- If no Precipitation chart: confirm the MCU sends value in 4th field; blanks become 0.0.
- If serial not opening:
  - Linux: `ls -l /dev/ttyUSB*` & ensure permissions (or add user to `dialout`).
  - Windows native: use TCP bridge strategy.
  - Set `SERIAL_PORT` explicitly instead of AUTO for stability.

Increase verbosity:
```bash
PRINT_EVERY_WRITE=1 SERIAL_PORT=/dev/ttyUSB0 ./run.sh
```

---
## 9. Customization
- Change CSV schema (add columns) via `CSV_SCHEMA`; then adapt `_parse_line_to_values` to populate them.
- Adjust flush durability: `_safe_fsync` can be modified if performance is an issue (remove fsync for higher throughput).
- Add aggregate rainfall logic in `app.py` if using cumulative gauges.

---
## 10. Security / API Keys
Keep your `OPENWEATHER_API_KEY` out of commits. Override at runtime:
```bash
OPENWEATHER_API_KEY=$(pass show openweather) ./run.sh
```

---
## 11. Troubleshooting Matrix
| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| No rows in table | Serial not connected / wrong port | Set `SERIAL_PORT` or use TCP bridge; ensure MCU is sending. |
| Only header in CSV | MCU hasn’t emitted valid line yet | Check wiring & baud, observe raw serial with `screen` or `miniterm`. |
| Weather metrics blank | API key missing / network | Set `OPENWEATHER_API_KEY`. |
| Windows: cannot access COM | Docker Desktop limitation | Use WSL path or TCP bridge (`SERIAL_TCP`). |
| Precipitation chart missing | All values None or column alias mismatch | Aliases normalized; ensure 4th value present. |

---
## 12. MCU Sender Template (Example)
```c
// Pseudocode
Serial.begin(115200);
void loop(){
  float tempC = readTemp();
  float hum = readHumidity();
  int light = readLight();
  int precip = readRainTicks();
  const char* level = classifyLevel(); // Low/Nominal/High
  Serial.print("DATA,");
  Serial.print(tempC,1); Serial.print(',');
  Serial.print(hum,1); Serial.print(',');
  Serial.print(light); Serial.print(',');
  Serial.print(precip); Serial.print(',');
  Serial.println(level);
  delay(2000);
}
```

---
## 13. License / Attribution
Add your preferred license here (MIT, Apache-2.0, etc.).

---
## 14. Quick Command Reference
| Action | Command |
|--------|---------|
| Build & run (Linux) | `sudo ./run.sh` |
| Build & run (Win PowerShell) | `./run_windows.ps1` |
| Override serial (Linux) | `SERIAL=/dev/ttyUSB1 ./run.sh` |
| Use TCP bridge (Windows) | `$env:SERIAL_TCP='localhost:7777'; ./run_windows.ps1` |
| Local (no Docker) | `streamlit run app.py` |
| Tail CSV | `tail -f data/data.csv` |

---
Happy monitoring! 🚀
