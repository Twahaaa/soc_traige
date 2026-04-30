#!/bin/bash
set -euo pipefail

# Launch the real-data pipeline in tmux.
# Trains NeuralLog on HDFS or BGL, then starts the live stream workers and the dataset-backed producer.
# Usage: ./scripts/run_real_pipeline.sh [hdfs|bgl] [count]

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="soc-triage-real-data"
DATASET="${1:-hdfs}"
COUNT="${2:-1000}"
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

if ! redis-cli PING >/dev/null 2>&1; then
  echo "[run] Redis is not running. Start Redis first."
  exit 1
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
fi

if [ "$DATASET" = "hdfs" ]; then
  MODEL_PATH="$ROOT/data/models/neurallog_hdfs.pt"
else
  MODEL_PATH="$ROOT/data/models/neurallog_bgl.pt"
fi

echo "[run] training NeuralLog on $DATASET"
uv run python -m detection.neurallog.train --dataset "$DATASET" --epochs 1 --max_lines "$COUNT" --output "$MODEL_PATH"

start_window() {
  local name="$1"
  local command="$2"
  tmux new-window -t "$SESSION" -n "$name" -c "$ROOT" bash -lc "$command"
}

tmux new-session -d -s "$SESSION" -n redis -c "$ROOT" bash -lc 'exec redis-cli PING'
tmux set-option -t "$SESSION" remain-on-exit on

redis-cli DEL stream:raw_logs stream:queue_a stream:queue_b stream:queue_b_escalated stream:results_normal stream:triage_reports >/dev/null 2>&1 || true

start_window "sequence_builder" 'until redis-cli PING >/dev/null 2>&1; do sleep 1; done; exec uv run python -m preprocessing.sequence_builder'
start_window "queue_a_worker" "until redis-cli PING >/dev/null 2>&1; do sleep 1; done; exec uv run python -m queue.queue_a_worker --model-path $MODEL_PATH"
start_window "queue_b_worker" "until redis-cli PING >/dev/null 2>&1; do sleep 1; done; exec uv run python -m queue.queue_b_worker --model-path $MODEL_PATH"

if [ "$DATASET" = "hdfs" ]; then
  DATASET_PATH="$ROOT/data/raw"
else
  DATASET_PATH="$ROOT/data/raw"
fi
start_window "producer" "until redis-cli PING >/dev/null 2>&1; do sleep 1; done; exec uv run python -m ingestion.producer --dataset_dir $DATASET_PATH --count $COUNT"

tmux select-window -t "$SESSION:sequence_builder"
tmux attach -t "$SESSION"
