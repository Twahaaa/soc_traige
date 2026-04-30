#!/bin/bash
set -Eeuo pipefail

# Launch the Stage 3 verification stack in tmux.
# One command starts Redis (if needed), the preprocessor, both queue workers, and the producer.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="soc-triage-stage3"
MODEL_PATH="$ROOT/data/models/neurallog.pt"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/run_pipeline.log"

cd "$ROOT"
[ -f .env ] && source .env || true
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

trap 'echo "[run] error at line ${LINENO}: ${BASH_COMMAND}"' ERR

echo "[run] logging to $LOG_FILE"

if [ ! -f "$MODEL_PATH" ]; then
  echo "[run] training NeuralLog checkpoint"
  uv run python -m detection.neurallog.train --dataset synthetic --epochs 1 --synthetic_count 80 --output "$MODEL_PATH"
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
fi

start_window() {
  local name="$1"
  local log_file="$2"
  local command="$3"
  tmux new-window -t "$SESSION" -n "$name" -c "$ROOT" bash -lc "set -Eeuo pipefail; exec > >(tee -a \"$log_file\") 2>&1; $command"
}

# The Redis window either starts the server or confirms it is already up.
redis_command='if redis-cli PING >/dev/null 2>&1; then echo "[redis] already running"; exec redis-cli PING; else echo "[redis] starting server"; exec redis-server --save "" --appendonly no; fi'
tmux new-session -d -s "$SESSION" -n redis -c "$ROOT" bash -lc "set -Eeuo pipefail; exec > >(tee -a \"$LOG_DIR/redis.log\") 2>&1; $redis_command"
tmux set-option -t "$SESSION" remain-on-exit on

until redis-cli PING >/dev/null 2>&1; do
  sleep 1
done

# Start from a clean test state.
redis-cli DEL stream:raw_logs stream:queue_a stream:queue_b stream:queue_b_escalated stream:results_normal stream:triage_reports >/dev/null 2>&1 || true

start_window "sequence_builder" "$LOG_DIR/sequence_builder.log" 'until redis-cli PING >/dev/null 2>&1; do sleep 1; done; uv run python -m preprocessing.sequence_builder'
start_window "queue_a_worker" "$LOG_DIR/queue_a_worker.log" 'until redis-cli PING >/dev/null 2>&1; do sleep 1; done; uv run python -m queue.queue_a_worker --model-path data/models/neurallog.pt'
start_window "queue_b_worker" "$LOG_DIR/queue_b_worker.log" 'until redis-cli PING >/dev/null 2>&1; do sleep 1; done; uv run python -m queue.queue_b_worker --model-path data/models/neurallog.pt'
start_window "producer" "$LOG_DIR/producer.log" 'until redis-cli PING >/dev/null 2>&1; do sleep 1; done; uv run python -m ingestion.producer --mode attack --rate 2 --count 80'

tmux select-window -t "$SESSION:sequence_builder"
tmux attach -t "$SESSION"
