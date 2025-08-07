#!/usr/bin/env bash
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

