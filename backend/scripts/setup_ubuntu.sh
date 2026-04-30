#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v sudo >/dev/null 2>&1; then
  echo "[setup] sudo is required on Ubuntu. Install it or run as a privileged user." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y tmux redis-server curl ca-certificates

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

if redis-cli PING >/dev/null 2>&1; then
  echo "[setup] Redis is already running"
else
  sudo systemctl enable --now redis-server 2>/dev/null || sudo service redis-server start
  until redis-cli PING >/dev/null 2>&1; do
    sleep 1
  done
  echo "[setup] Started Redis"
fi

echo "[setup] Ubuntu environment ready"
