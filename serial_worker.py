# serial_worker.py — write EACH reading immediately (flush+fsync per line)
import os, time, threading, sys, platform, socket
from datetime import datetime
from pathlib import Path

import serial
from serial.serialutil import SerialException

# -------- Env --------
SERIAL_PORT = os.getenv("SERIAL_PORT", "AUTO")  # "AUTO" will scan common ports (incl. Windows COM*)
SERIAL_TCP  = os.getenv("SERIAL_TCP", "").strip()  # e.g. host:7777 or tcp://host:7777 to read lines via TCP bridge
BAUDRATE    = int(os.getenv("BAUDRATE", "115200"))   # must match Serial.begin() on receiver
SLEEP_SEC   = float(os.getenv("SLEEP_SEC", "0.02"))

CSV_PATH    = Path(os.getenv("CSV_PATH", "data.csv"))
CSV_SCHEMA  = os.getenv(
    "CSV_SCHEMA",
    "EntryTimeUTC,Latitude,Longitude,Temperature,Humidity,Light,Precipitation,WaterLevel"
)

# Optional prefix (we'll accept lines with or without it)
DATA_PREFIX = os.getenv("DATA_PREFIX", "DATA,")

# Default location (added to each row)
DEFAULT_LAT = os.getenv("DEFAULT_LAT", "")
DEFAULT_LON = os.getenv("DEFAULT_LON", "")

# Print a log line for EVERY write (set to "0" to quiet)
PRINT_EVERY_WRITE = os.getenv("PRINT_EVERY_WRITE", "1") == "1"

CSV_COLS = [c.strip() for c in CSV_SCHEMA.split(",")]
PAYLOAD_KEYS = ["temperature","humidity","light","precipitation","waterlevel"]

# -------- CSV helpers (durable) --------
def _safe_fsync(f):
    try:
        os.fsync(f.fileno())
    except Exception:
        # On some filesystems / platforms fsync may fail (network / emulated FS); ignore to keep loop alive
        pass

def _ensure_header():
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    need_header = (not CSV_PATH.exists()) or (CSV_PATH.stat().st_size == 0)
    if need_header:
        with CSV_PATH.open("w", encoding="utf-8") as f:
            f.write(",".join(CSV_COLS) + "\n")
            f.flush(); _safe_fsync(f)

def _append_row(values):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("a", encoding="utf-8") as f:
        f.write(",".join(values) + "\n")
    f.flush(); _safe_fsync(f)

# -------- Parsing --------
def _parse_line_to_values(line: str):
    """
    Accepts:
      "temp,hum,light,precip,level"              (no prefix)
      "DATA,temp,hum,light,precip,level"         (with prefix)

    temp/hum: floats (e.g., 23.0)
    light/precip: ints
    level: int or token (we keep as-is if it's numeric)

    Returns list[str] ordered to match CSV_COLS except EntryTimeUTC (added later),
    or None to skip.
    """
    s = line.strip()
    if not s:
        return None

    if DATA_PREFIX and s.startswith(DATA_PREFIX):
        s = s[len(DATA_PREFIX):].lstrip()

    parts = [p.strip() for p in s.split(",")]
    if len(parts) < 5:
        return None

    try:
        temp   = float(parts[0])
        hum    = float(parts[1])
        light  = int(float(parts[2]))   # tolerate "22276.0"
        precip = int(float(parts[3]))
    except ValueError:
        return None

    lvl_raw = parts[4]
    # Keep numeric levels as-is; otherwise store token
    try:
        lvl_out = str(int(float(lvl_raw)))
    except ValueError:
        lvl_out = lvl_raw  # e.g., "Low"/"Nominal"/"High"/"Unknown"

    values = []
    for col in CSV_COLS:
        key = col.strip().lower()
        if key == "entrytimeutc":
            continue
        elif key == "latitude":
            values.append(str(DEFAULT_LAT))
        elif key == "longitude":
            values.append(str(DEFAULT_LON))
        elif key == "temperature":
            values.append(f"{temp:.1f}")
        elif key == "humidity":
            values.append(f"{hum:.1f}")
        elif key == "light":
            values.append(str(light))
        elif key == "precipitation":
            values.append(str(precip))
        elif key == "waterlevel":
            values.append(lvl_out)
        else:
            values.append("")
    return values

# -------- Serial loop --------
_stop = threading.Event()
_thread = None

def _list_candidate_ports():
    """Return a list of candidate serial port names to try, depending on platform and env SERIAL_PORT.

    If SERIAL_PORT is not AUTO, just return that single value.
    """
    env_port = SERIAL_PORT.strip()
    if env_port.upper() != "AUTO":
        return [env_port]

    # AUTO mode
    platsys = platform.system().lower()
    candidates = []
    if platsys == "windows":
        # Typical COM range (avoid huge list). We will also query pyserial for real ports.
        try:
            from serial.tools import list_ports
            detected = [p.device for p in list_ports.comports()]
        except Exception:
            detected = []
        # Favor detected ones first, then a short COM range fallback
        fallback = [f"COM{i}" for i in range(3, 12)]
        for p in detected + fallback:
            if p not in candidates:
                candidates.append(p)
    else:
        # POSIX: common USB/UART names
        common = [
            "/dev/ttyUSB0","/dev/ttyUSB1","/dev/ttyUSB2",
            "/dev/ttyACM0","/dev/ttyACM1",
            "/dev/ttyS0","/dev/ttyS1",
            "/dev/ttyTHS1",  # Jetson
        ]
        # Also attempt glob expansion for /dev/ttyUSB* etc.
        try:
            import glob
            globbed = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyTHS*")
        except Exception:
            globbed = []
        for p in globbed + common:
            if p not in candidates:
                candidates.append(p)
    if not candidates:
        # Last resort platform-based default
        return ["COM3" if os.name == "nt" else "/dev/ttyUSB0"]
    return candidates

def _open_serial():
    # TCP bridge mode overrides direct serial access
    if SERIAL_TCP:
        target = SERIAL_TCP
        if target.startswith("tcp://"):
            target = target[6:]
        if ':' not in target:
            print(f"[worker] SERIAL_TCP invalid (need host:port): {SERIAL_TCP}", file=sys.stderr, flush=True)
        else:
            host, port_s = target.rsplit(':',1)
            try:
                port_i = int(port_s)
            except ValueError:
                port_i = None
            if port_i is not None:
                while not _stop.is_set():
                    try:
                        sock = socket.create_connection((host, port_i), timeout=5)
                        sock.settimeout(2)
                        print(f"[worker] tcp bridge connected: {host}:{port_i}", flush=True)
                        return _SocketLineReader(sock)
                    except Exception as e:
                        print(f"[worker] tcp connect failed: {e} (retry 2s)", file=sys.stderr, flush=True)
                        time.sleep(2)
                return None

    kwargs = {}
    if os.name == "posix":
        # exclusive only available on posix; ignore errors if unsupported.
        kwargs["exclusive"] = True

    tried_once = False
    while not _stop.is_set():
        for port in _list_candidate_ports():
            if _stop.is_set():
                break
            try:
                ser = serial.Serial(port, BAUDRATE, timeout=1, **kwargs)
                print(f"[worker] serial open: {port} @ {BAUDRATE}", flush=True)
                return ser
            except Exception as e:
                # Only print failures after first full sweep or if env specified concrete port
                if SERIAL_PORT.strip().upper() != "AUTO" or tried_once:
                    print(f"[worker] serial open failed for {port}: {e}", file=sys.stderr, flush=True)
                time.sleep(0.1)
        tried_once = True
        print("[worker] no serial port open (retrying in 2s)...", flush=True)
        time.sleep(2)
    return None

class _SocketLineReader:
    """Minimal wrapper to present a readline()/close() API like pyserial for a TCP socket."""
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._buf = b''
    def readline(self):
        if not self.sock:
            return b''
        try:
            while b'\n' not in self._buf:
                chunk = self.sock.recv(1024)
                if not chunk:
                    # remote closed
                    return b''
                self._buf += chunk
        except socket.timeout:
            # return empty so caller can loop / sleep
            return b''
        except Exception:
            return b''
        line, _, rest = self._buf.partition(b'\n')
        self._buf = rest
        return line + b'\n'
    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

def _utc_now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def _read_loop():
    _ensure_header()
    ser = _open_serial()
    if ser is None:
        return

    while not _stop.is_set():
        try:
            raw = ser.readline()
            if not raw:
                # tiny sleep so we don’t hot-loop when idle
                time.sleep(SLEEP_SEC)
                continue

            try:
                line = raw.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue

            vals = _parse_line_to_values(line)
            if not vals:
                # print every reject so you can see what’s arriving (comment out if noisy)
                print(f"[worker] skip: {line}", flush=True)
                continue

            ts = _utc_now_iso()
            _append_row([ts] + vals)
            if PRINT_EVERY_WRITE:
                print(f"[worker] wrote: {line} -> {CSV_PATH}", flush=True)

        except (SerialException, OSError) as e:
            print(f"[worker] serial error: {e} — reopening in 2s", file=sys.stderr, flush=True)
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(2)
            ser = _open_serial()
            if ser is None:
                break
        except Exception as e:
            print(f"[worker] loop error: {e}", file=sys.stderr, flush=True)
            time.sleep(0.1)

    try:
        ser.close()
    except Exception:
        pass
    print("[worker] stopped.", flush=True)

# -------- Public API --------
def start_worker():
    global _thread
    if _thread and _thread.is_alive():
        return _thread
    _stop.clear()
    _thread = threading.Thread(target=_read_loop, daemon=True)
    _thread.start()
    return _thread

def stop_worker():
    _stop.set()
    t = _thread
    if t:
        t.join(timeout=2)
