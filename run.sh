#!/usr/bin/env bash
set -euo pipefail

# ---- Config (override via env if you want) ----
IMAGE="${IMAGE:-flood-monitoring}"
SERIAL="${SERIAL:-/dev/ttyUSB0}"   # e.g. /dev/ttyUSB0 or /dev/ttyTHS1
CSV_DIR="${CSV_DIR:-$PWD/data}"    # host folder to store CSV
CSV_FILE="${CSV_FILE:-data.csv}"   # file name inside CSV_DIR
PORT="${PORT:-8501}"
# -----------------------------------------------

export OPENWEATHER_API_KEY="1e9b1550861b51e90de8f1b39b3b870c"
export DEFAULT_LAT="29.58145"
export DEFAULT_LON="-98.616441"

docker rm -f floodDash >/dev/null 2>&1 || true

echo "🔧 Building image: $IMAGE"
docker build -t "$IMAGE" .

echo "🔍 Checking serial device..."
if [[ ! -e "$SERIAL" ]]; then
  echo "❌ Serial device $SERIAL not found."
  echo "   Hint: set SERIAL=/dev/ttyTHS1 (Jetson UART) or SERIAL=/dev/ttyUSB0 (USB)."
  exit 1
fi
echo "✅ Serial device $SERIAL found"

echo "📁 Preparing CSV directory: $CSV_DIR"
mkdir -p "$CSV_DIR"
# quick write test so we know the mount will be writable
if ! ( : > "$CSV_DIR/$CSV_FILE" ); then
  echo "❌ Cannot write to $CSV_DIR"
  exit 1
fi
echo "✅ CSV path OK → $CSV_DIR/$CSV_FILE"
echo "ℹ️  DB checks skipped (CSV mode)."

echo "🚀 Starting the container..."
echo "   - Streamlit: http://localhost:$PORT"
echo "   - Writing CSV to: $CSV_DIR/$CSV_FILE"

docker run -it \
  --name floodDash \
  -p "$PORT:$PORT" \
  --device "$SERIAL:$SERIAL" \
  -e "OPENWEATHER_API_KEY=$OPENWEATHER_API_KEY" \
  -e "DEFAULT_LAT=$DEFAULT_LAT" \
  -e "DEFAULT_LON=$DEFAULT_LON" \
  -e "CSV_PATH=/app/data/$CSV_FILE" \
  -e "SERIAL_PORT=$SERIAL" \
  -e "BAUDRATE=115200" \
  -v "$CSV_DIR:/app/data" \
  "$IMAGE"

