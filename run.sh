#!/usr/bin/env bash
set -e

IMAGE="esp32-dashboard"
SERIAL="/dev/ttyUSB0"   # adjust if your Jetson Nano UART is different

echo "🔨 Building the Docker image..."
docker build -t "$IMAGE" .

echo "🔍 Checking if serial device exists..."
if [ -e "$SERIAL" ]; then
    echo "✅ Serial device $SERIAL found"
    DEVICE_ARG="--device $SERIAL:$SERIAL"
else
    echo "⚠️  Serial device $SERIAL not found - continuing without it"
    DEVICE_ARG=""
fi

echo "🚀 Starting the container..."
echo "   - Streamlit will be available at: http://localhost:8501"
echo "   - Using --network host for database connectivity"
echo "   - Press Ctrl+C to stop"
echo ""

# Run it, sharing the host's network so localhost→Postgres works
# and passing the serial port through if it exists
docker run --rm \
  --network host \
  $DEVICE_ARG \
  "$IMAGE"
set -e

IMAGE="esp32-dashboard"
SERIAL="/dev/ttyUSB0"   # adjust if your Jetson Nano UART is different

# Build the image
docker build -t "$IMAGE" .

# Run it, sharing the host’s network so localhost→Postgres works
# and passing the serial port through
docker run --rm \
  --network host \
  --device "$SERIAL:$SERIAL" \
  "$IMAGE"

