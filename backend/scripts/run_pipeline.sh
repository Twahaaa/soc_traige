#!/bin/bash
set -euo pipefail

# Launch the Stage 3 verification stack in tmux.
# One command starts Redis (if needed), the preprocessor, both queue workers, and the producer.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="soc-triage-stage3"
MODEL_PATH="$ROOT/data/models/neurallog.pt"

cd "$ROOT"
source .env 2>/dev/null || true

if [ ! -f "$MODEL_PATH" ]; then
  echo "[run] training NeuralLog checkpoint"
  uv run python -m detection.neurallog.train --dataset synthetic --epochs 1 --synthetic_count 80 --output "$MODEL_PATH"
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
fi

start_window() {
  local name="$1"
  local command="$2"
  tmux new-window -t "$SESSION" -n "$name" -c "$ROOT" bash -lc "$command"
}

# The Redis window either starts the server or confirms it is already up.
redis_command='if redis-cli PING >/dev/null 2>&1; then echo "[redis] already running"; exec redis-cli PING; else echo "[redis] starting server"; exec redis-server --save "" --appendonly no; fi'
tmux new-session -d -s "$SESSION" -n redis -c "$ROOT" bash -lc "$redis_command"
tmux set-option -t "$SESSION" remain-on-exit on

until redis-cli PING >/dev/null 2>&1; do
  sleep 1
done

# Start from a clean test state.
redis-cli DEL stream:raw_logs stream:queue_a stream:queue_b stream:queue_b_escalated stream:results_normal stream:triage_reports >/dev/null 2>&1 || true

start_window "sequence_builder" 'until redis-cli PING >/dev/null 2>&1; do sleep 1; done; exec uv run python -m preprocessing.sequence_builder'
start_window "queue_a_worker" 'until redis-cli PING >/dev/null 2>&1; do sleep 1; done; exec uv run python -m queue.queue_a_worker --model-path data/models/neurallog.pt'
start_window "queue_b_worker" 'until redis-cli PING >/dev/null 2>&1; do sleep 1; done; exec uv run python -m queue.queue_b_worker --model-path data/models/neurallog.pt'
start_window "producer" 'until redis-cli PING >/dev/null 2>&1; do sleep 1; done; exec uv run python -m ingestion.producer --mode attack --rate 2 --count 80'

tmux select-window -t "$SESSION:sequence_builder"
tmux attach -t "$SESSION"
