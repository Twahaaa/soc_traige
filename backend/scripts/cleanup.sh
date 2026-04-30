#!/bin/bash
set -Eeuo pipefail

# Stop the Stage 3 tmux session and clear local pipeline artifacts.
# Use `--full` to flush the Redis database instead of only deleting the pipeline streams.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="soc-triage-stage3"
FULL=false
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/cleanup.log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

trap 'echo "[cleanup] error at line ${LINENO}: ${BASH_COMMAND}"' ERR

echo "[cleanup] logging to $LOG_FILE"

for arg in "$@"; do
  case "$arg" in
    --full)
      FULL=true
      ;;
    --session)
      echo "usage: $0 [--full]" >&2
      exit 1
      ;;
    *)
      echo "usage: $0 [--full]" >&2
      exit 1
      ;;
  esac
done

cd "$ROOT"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
  echo "[cleanup] stopped tmux session $SESSION"
else
  echo "[cleanup] tmux session $SESSION not running"
fi

if redis-cli PING >/dev/null 2>&1; then
  if [ "$FULL" = true ]; then
    redis-cli FLUSHDB >/dev/null
    echo "[cleanup] flushed Redis database"
  else
    redis-cli DEL stream:raw_logs stream:queue_a stream:queue_b stream:queue_b_escalated stream:results_normal stream:triage_reports >/dev/null
    echo "[cleanup] cleared pipeline streams"
  fi
else
  echo "[cleanup] Redis not reachable, skipped stream cleanup"
fi

rm -f data/models/neurallog*.pt

shopt -s nullglob
for cache_file in data/embeddings/*.npy; do
  rm -f "$cache_file"
done
shopt -u nullglob

echo "[cleanup] removed NeuralLog checkpoint and cached embeddings"
