#!/bin/bash
set -Eeuo pipefail

# Launch the real-data pipeline in tmux.
# Trains NeuralLog on HDFS or BGL, then starts the live stream workers and the dataset-backed producer.
# Usage: ./scripts/run_real_pipeline.sh [hdfs|bgl] [count]

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="soc-triage-real-data"
DATASET="${1:-hdfs}"
COUNT="${2:-1000}"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/run_real_pipeline-${DATASET}.log"
case "$DATASET" in
  hdfs|bgl)
    ;;
  *)
    echo "usage: $0 [hdfs|bgl]" >&2
    exit 1
    ;;
esac

cd "$ROOT"
source .env 2>/dev/null || true
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

trap 'echo "[run] error at line ${LINENO}: ${BASH_COMMAND}"' ERR

echo "[run] logging to $LOG_FILE"

require_command() {
  local command_name="$1"
  local install_hint="$2"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "[run] missing '$command_name'. Install with: $install_hint" >&2
    exit 1
  fi
}

require_command tmux "Run ./scripts/setup.sh for your OS."
require_command redis-cli "Run ./scripts/setup.sh for your OS."
require_command redis-server "Run ./scripts/setup.sh for your OS."
require_command uv "Run ./scripts/setup.sh for your OS."

if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
fi

if [ "$DATASET" = "hdfs" ]; then
  MODEL_PATH="$ROOT/data/models/neurallog_hdfs.pt"
  DATASET_FILE="$ROOT/data/raw/HDFS.log"
else
  MODEL_PATH="$ROOT/data/models/neurallog_bgl.pt"
  DATASET_FILE="$ROOT/data/raw/BGL.log"
fi

echo "[run] training NeuralLog on $DATASET"
uv run python -m detection.neurallog.train --dataset "$DATASET" --epochs 1 --max_lines "$COUNT" --output "$MODEL_PATH"

start_window() {
  local name="$1"
  local log_file="$2"
  local command="$3"
  tmux new-window -t "$SESSION" -n "$name" -c "$ROOT" bash -lc "set -Eeuo pipefail; exec > >(tee -a \"$log_file\") 2>&1; $command"
}

redis_command='if redis-cli PING >/dev/null 2>&1; then echo "[redis] already running"; exec redis-cli PING; else echo "[redis] starting server"; exec redis-server --save "" --appendonly no; fi'
tmux new-session -d -s "$SESSION" -n redis -c "$ROOT" bash -lc "set -Eeuo pipefail; exec > >(tee -a \"$LOG_DIR/redis.log\") 2>&1; $redis_command"
tmux set-option -t "$SESSION" remain-on-exit on

until redis-cli PING >/dev/null 2>&1; do
  sleep 1
done

redis-cli DEL stream:raw_logs stream:queue_a stream:queue_b stream:queue_b_escalated stream:results_normal stream:triage_reports >/dev/null 2>&1 || true

start_window "sequence_builder" "$LOG_DIR/sequence_builder.log" 'until redis-cli PING >/dev/null 2>&1; do sleep 1; done; uv run python -m preprocessing.sequence_builder'
start_window "queue_a_worker" "$LOG_DIR/queue_a_worker.log" "until redis-cli PING >/dev/null 2>&1; do sleep 1; done; uv run python -m queue.queue_a_worker --model-path \"$MODEL_PATH\""
start_window "queue_b_worker" "$LOG_DIR/queue_b_worker.log" "until redis-cli PING >/dev/null 2>&1; do sleep 1; done; uv run python -m queue.queue_b_worker --model-path \"$MODEL_PATH\""

start_window "producer" "$LOG_DIR/producer.log" "until redis-cli PING >/dev/null 2>&1; do sleep 1; done; uv run python -m ingestion.producer --file \"$DATASET_FILE\" --count \"$COUNT\""

tmux select-window -t "$SESSION:sequence_builder"
tmux attach -t "$SESSION"
