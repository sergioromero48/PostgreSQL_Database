#!/usr/bin/env bash
set -euo pipefail

# ---- Config you can override via env ----
IMAGE="${IMAGE:-esp32-dashboard}"
PORT="${PORT:-8501}"
SERIAL="${SERIAL:-/dev/ttyUSB0}"
CSV_DIR="${CSV_DIR:-$PWD/data}"
CSV_FILE="${CSV_FILE:-data.csv}"
# ----------------------------------------

echo "🔨 Building the Docker image: $IMAGE"
docker build -t "$IMAGE" .

# Ensure the CSV dir exists and the file has a header
mkdir -p "$CSV_DIR"
CSV_PATH="$CSV_DIR/$CSV_FILE"
if [ ! -s "$CSV_PATH" ]; then
  echo "EntryTime,PrecipInInches,HumidityInPercentage,TemperatureInFahrenheit,WaterLevel" > "$CSV_PATH"
  echo "📝 Wrote CSV header to $CSV_PATH"
fi

# Only pass the serial device if it's present
DEVICE_ARG=()
if [ -e "$SERIAL" ]; then
  echo "✅ Serial device found: $SERIAL"
  DEVICE_ARG=(--device "$SERIAL:$SERIAL")
else
  echo "⚠️  Serial device $SERIAL not found — running without it"
fi

# Clean any old container
docker rm -f esp32dash >/dev/null 2>&1 || true

# Run container; mount data dir; expose port; set envs; force a good entrypoint
docker run -d --name esp32dash \
  -p "$PORT:8501" \
  -v "$CSV_DIR:/app/data" \
  -e "CSV_PATH=/app/data/$CSV_FILE" \
  -e "SERIAL_PORT=$SERIAL" \
  -e "BAUDRATE=115200" \
  "${DEVICE_ARG[@]}" \
  --entrypoint bash \
  "$IMAGE" -lc 'streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true'

echo "🚀 Up at http://localhost:$PORT"

