#!/usr/bin/env bash
set -euo pipefail
# Simple Docker install using distro packages (Debian/Ubuntu). Provides docker.io + docker-compose plugin.
# Pros: very quick, fewer steps. Cons: version may lag upstream.

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

echo "[+] Updating package index"
apt-get update -y

echo "[+] Installing docker.io and plugins"
apt-get install -y docker.io docker-compose-plugin || apt-get install -y docker.io

echo "[+] Enabling and starting service"
systemctl enable docker
systemctl restart docker

# Add non-root user to docker group
TARGET_USER=$(logname 2>/dev/null || echo ${SUDO_USER:-})
if [[ -n "$TARGET_USER" ]]; then
  usermod -aG docker "$TARGET_USER" || true
  echo "[i] User $TARGET_USER added to docker group (log out/in to use without sudo)."
fi

echo "[✓] Done. Test: docker run --rm hello-world" 
