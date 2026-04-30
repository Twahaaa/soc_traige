#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v brew >/dev/null 2>&1; then
  echo "[setup] Homebrew is required on macOS. Install it from https://brew.sh" >&2
  exit 1
fi

install_if_missing() {
  local formula="$1"
  if brew list "$formula" >/dev/null 2>&1; then
    echo "[setup] $formula already installed"
  else
    brew install "$formula"
  fi
}

install_if_missing tmux
install_if_missing redis
install_if_missing uv

if redis-cli PING >/dev/null 2>&1; then
  echo "[setup] Redis is already running"
else
  brew services start redis >/dev/null
  until redis-cli PING >/dev/null 2>&1; do
    sleep 1
  done
  echo "[setup] Started Redis with brew services"
fi

echo "[setup] macOS environment ready"
