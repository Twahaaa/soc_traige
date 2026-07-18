#!/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/setup-qdrant.log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

trap 'echo "[setup] error at line ${LINENO}: ${BASH_COMMAND}"' ERR

if ! command -v docker >/dev/null 2>&1; then
  echo "[setup] docker is required to start Qdrant" >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx qdrant; then
  if docker ps --format '{{.Names}}' | grep -qx qdrant; then
    echo "[setup] Qdrant already running"
  else
    docker start qdrant
    echo "[setup] started existing Qdrant container"
  fi
else
  docker run -d --name qdrant --restart unless-stopped -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest
  echo "[setup] started Qdrant"
fi

for _ in {1..30}; do
  if curl -fsS http://localhost:6333/healthz >/dev/null 2>&1; then
    echo "[setup] Qdrant is healthy on http://localhost:6333"
    exit 0
  fi
  sleep 1
done

echo "[setup] Qdrant started but health check did not pass in time" >&2
exit 1
