# SOC Triage System — Architecture Document

> **Generated:** 2026-07-14  
> **Branch:** `twaha-backend`  
> **Commit:** `00b029d` (Stage 4 triage + setup flow completed)  
> **Status:** Stages 1–3 COMPLETE, Stage 4 PARTIAL (agents + tools work, verification pending), Stage 5 NOT STARTED

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture & Data Flow](#2-system-architecture--data-flow)
3. [Redis Stream Topology](#3-redis-stream-topology)
4. [Qdrant Vector Database](#4-qdrant-vector-database)
5. [Configuration System](#5-configuration-system)
6. [Stage 1: Log Ingestion & Prefiltering](#6-stage-1-log-ingestion--prefiltering)
7. [Stage 2: Preprocessing & Sequence Construction](#7-stage-2-preprocessing--sequence-construction)
8. [Stage 3: Anomaly Detection (NeuralLog)](#8-stage-3-anomaly-detection-neurallog)
9. [Stage 4: LLM Triage & Report Storage](#9-stage-4-llm-triage--report-storage)
10. [Stage 5: Dashboard (Not Started)](#10-stage-5-dashboard-not-started)
11. [Evaluation Package (Not Started)](#11-evaluation-package-not-started)
12. [DeepLog Baseline (Stub)](#12-deeplog-baseline-stub)
13. [Frontend Application](#13-frontend-application)
14. [CI/CD Pipeline](#14-cicd-pipeline)
15. [Scripts & Automation](#15-scripts--automation)
16. [Data Flow Walkthrough](#16-data-flow-walkthrough)
17. [Known Gaps & Future Work](#17-known-gaps--future-work)
18. [Security Considerations](#18-security-considerations)

---

## 1. Project Overview

The **SOC Triage System** automates the detection, analysis, and prioritization of security alerts from system logs. It uses a five-stage streaming pipeline:

1. **Ingestion** — ingests raw log lines, applies rule-based prefiltering, publishes to Redis
2. **Preprocessing** — tokenizes logs, builds sliding windows, routes by priority
3. **Anomaly Detection** — NeuralLog (BERT + Transformer) scores each window
4. **LLM Triage** — a LangChain-based agent with 4 tools generates structured reports
5. **Dashboard** — FastAPI + Next.js UI for alert visualization (not yet built)

### Technology Stack

| Component | Technology | Version | Notes |
|-----------|-----------|---------|-------|
| Language | Python | >= 3.11 | Managed via `uv` |
| Web framework | FastAPI | >= 0.135.3 | For future dashboard API |
| ASGI server | uvicorn | >= 0.44.0 | For dashboard |
| ML framework | PyTorch | >= 2.11.0 | NeuralLog model |
| NLP | transformers | >= 5.7.0 | BERT embeddings |
| Embeddings | sentence-transformers | >= 5.4.1 | Report similarity |
| LLM orchestration | LangChain | >= 1.2.15 | Groq + Ollama integration |
| LLM Provider (primary) | Groq (ChatGroq) | llama-3.1-8b-instant | Agent backend |
| LLM Provider (fallback) | Ollama (ChatOllama) | gemma3:4b | Deterministic path |
| Vector DB | Qdrant | >= 1.17.1 | Docker, collection `triage_reports` |
| Queue | Redis | >= 7.4.0 | Streams + consumer groups |
| Data | numpy, pandas | numpy>=2.4.4, pandas>=3.0.2 | Data handling |
| Validation | pydantic | >= 2.13.0 | Schemas |
| Config | PyYAML | >= 6.0.3 | settings.yaml |
| Env vars | python-dotenv | >= 1.2.2 | API keys |
| Frontend | Next.js | 16.2.3 | App Router, TypeScript |
| Frontend styling | Tailwind CSS | v4 | PostCSS |
| Linting (Python) | ruff | CI-only | via uv |
| Testing | pytest | CI-only | No tests written yet |
| CI | GitHub Actions | — | PRs to `main` |

### Package Manager

Python dependencies are managed via **`uv`** (Astral). Lock file: `uv.lock` (3303 lines). Frontend uses **npm**.

---

## 2. System Architecture & Data Flow

### High-Level Pipeline

```
                     ┌──────────────────────────────────────────┐
                     │              STAGE 1                     │
                     │                                          │
  [Synthetic Logs]───►  Producer  ──►  PreFilter  ──► stream:raw_logs
  [HDFS.log]──────────┤              (keyword/                   │
  [BGL.log]───────────┤               regex/                     │
                      │               brute-force)               │
                      └──────────────────────────────────────────┘
                                          │
                                          │ XREADGROUP
                                          ▼
                      ┌──────────────────────────────────────────┐
                      │              STAGE 2                     │
                      │  SequenceBuilder                          │
                      │  ─ tokenize (parsing-free regex)          │
                      │  ─ sliding window (size=20, step=1)       │
                      │  ─ choose_stream (priority-based route)   │
                      └─────┬────────────────────┬────────────────┘
                      normal│                    │critical
                            ▼                    ▼
                  ┌──────────────────┐  ┌──────────────────┐
                  │   STAGE 3        │  │   STAGE 3        │
                  │ stream:queue_a   │  │ stream:queue_b   │
                  │       │          │  │       │          │
                  │ QueueAWorker     │  │ QueueBWorker     │
                  │ ─ NeuralLog      │  │ ─ NeuralLog      │
                  │   inference      │  │   inference      │
                  │ ─ score > 0.5?   │  │ ─ always triage  │
                  └──────┬───────────┘  └───────┬──────────┘
                    normal│    anomaly│         │
                         ▼        ▼             │
                  ┌──────────┐ ┌──────────┐     │
                  │ results  │ │ queue_b  │     │
                  │ _normal  │ │_escalated│     │
                  └──────────┘ └────┬─────┘     │
                                   │           │
                                   ▼           ▼
                            ┌──────────────────────┐
                            │     STAGE 4           │
                            │  stream:queue_b       │
                            │  stream:queue_b_escal. │
                            │     │                 │
                            │  QueueBWorker         │
                            │  ─ normalize message  │
                            │  ─ TriageAgent.run()  │
                            │     │                 │
                            │  ┌──▼──────────────┐  │
                            │  │  TriageAgent     │  │
                            │  │  ┌─ tools ─────┐ │  │
                            │  │  │ CVE Lookup  │ │  │
                            │  │  │ IP Reputation│ │  │
                            │  │  │ Historical   │ │  │
                            │  │  │ MITRE Mapper │ │  │
                            │  │  └─────────────┘ │  │
                            │  │  LLM (Groq/Ollama)│  │
                            │  │  → TriageReport  │  │
                            │  └──────────────────┘  │
                            │     │                  │
                            │  ┌──▼──────────────┐   │
                            │  │  Storage         │   │
                            │  │  ─ Qdrant upsert │   │
                            │  │  ─ Redis publish │   │
                            │  └──────────────────┘   │
                            └──────────────────────┘
                                          │
                                   stream:triage_reports
                                          │
                                          ▼
                            ┌──────────────────────┐
                            │     STAGE 5 (TODO)   │
                            │  FastAPI Dashboard   │
                            │  WebSocket feed      │
                            │  Next.js UI          │
                            └──────────────────────┘
```

### Data Flow Summary

1. **Log source** → `Producer` reads from synthetic generator, file, or dataset directory
2. **PreFilter** classifies each line as `normal` or `critical` (with a reason string)
3. **Producer** publishes `{log_line, timestamp, priority, source, prefilter_reason}` to `stream:raw_logs`
4. **SequenceBuilder** consumes via `XREADGROUP`, tokenizes, fills a deque window (size=20), then routes the window to `stream:queue_a` (normal) or `stream:queue_b` (critical)
5. **QueueAWorker** runs NeuralLog inference on normal windows; anomalies get escalated to `stream:queue_b_escalated`; normal results go to `stream:results_normal`
6. **QueueBWorker** reads from `stream:queue_b` AND `stream:queue_b_escalated`; runs NeuralLog on `queue_b` items (fast-path criticals) to get anomaly score; passes combined message to `TriageAgent.run()`
7. **TriageAgent** runs all 4 tools in parallel, calls LLM (Groq or Ollama), builds a `TriageReport`, upserts into Qdrant, publishes to `stream:triage_reports`
8. **Dashboard** (future) would consume `stream:triage_reports` and serve a WebSocket feed + REST API

---

## 3. Redis Stream Topology

### Connection

```python
redis.Redis(host="localhost", port=6379, decode_responses=True)
```

All stream values are strings. Nested structures (sequences, raw_lines) are JSON-encoded strings.

### Streams and Consumer Groups

| Stream | Consumer Group | Producer(s) | Consumer(s) |
|--------|---------------|-------------|-------------|
| `stream:raw_logs` | `group:preprocessing` | `Producer` (Stage 1) | `SequenceBuilder` (Stage 2) |
| `stream:queue_a` | `group:queue_a` | `SequenceBuilder` (Stage 2) | `QueueAWorker` (Stage 3) |
| `stream:queue_b` | `group:queue_b` | `SequenceBuilder` (Stage 2) | `QueueBWorker` (Stage 3) |
| `stream:queue_b_escalated` | `group:queue_b` (shared) | `QueueAWorker` (Stage 3) | `QueueBWorker` (Stage 3) |
| `stream:results_normal` | `group:dashboard` | `QueueAWorker` (Stage 3) | Dashboard (future) |
| `stream:triage_reports` | `group:dashboard` | `TriageAgent` (Stage 4) | Dashboard (future) |

### Stream Message Schemas

**`stream:raw_logs`** (single log line):
```json
{
  "log_line": "string",
  "timestamp": "2024-05-15T10:23:01+00:00",
  "priority": "normal|critical",
  "source": "synthetic|hdfs|bgl|filename",
  "prefilter_reason": "null|keyword_match:CRITICAL|privilege_escalation|brute_force:203.0.113.10"
}
```

**`stream:queue_a` / `stream:queue_b`** (window payload):
| Field | Type | Description |
|-------|------|-------------|
| `sequence` | JSON string | List of token lists: `[["token1", "token2"], ...]` (size=20) |
| `raw_lines` | JSON string | List of raw log strings (size=20) |
| `priority` | string | `"normal"` or `"critical"` |
| `window_start_ts` | string | Timestamp of first log in window |
| `window_end_ts` | string | Timestamp of last log in window |
| `source` | string | `"synthetic"`, `"hdfs"`, `"bgl"`, or filename |

**`stream:queue_b_escalated`** (from QueueAWorker):
| Field | Type | Description |
|-------|------|-------------|
| Same as queue_a/b PLUS | ... | ... |
| `anomaly_score` | string (float) | NeuralLog sigmoid output |
| `priority` | string | Inherited from source |

**`stream:results_normal`** (benign results):
| Field | Type | Description |
|-------|------|-------------|
| Same as queue_a/b PLUS | ... | ... |
| `anomaly_score` | string (float) | NeuralLog score |
| `label` | string | `"normal"` |

**`stream:triage_reports`**:
| Field | Type | Description |
|-------|------|-------------|
| `report` | JSON string | Full `TriageReport.model_dump_json()` |

### Consumer Group Details

- `group:queue_b` is shared across BOTH `stream:queue_b` AND `stream:queue_b_escalated`
- QueueBWorker reads both streams in a single `XREADGROUP` call
- All consumers use `id="$"` (new messages only) and auto-create streams via `mkstream=True`
- Acknowledgment happens in `finally` block after processing (at-least-once delivery)

---

## 4. Qdrant Vector Database

### Connection

```python
QdrantClient(host="localhost", port=6333, check_compatibility=False)
```

### Collection: `triage_reports`

| Parameter | Value |
|-----------|-------|
| Vector size | 384 |
| Distance metric | Cosine |
| Embedding model | `all-MiniLM-L6-v2` (sentence-transformers) |

### Vector Derivation

For `TriageReport` embeddings:
```
text = f"{report.title} {report.description} {' '.join(report.remediation_steps)}"
vector = report_embedder.encode(text, normalize_embeddings=True)
```

**Fallback**: If `all-MiniLM-L6-v2` model is unavailable, a deterministic pseudo-random embedding is generated using `hashlib.md5` of the text as seed (`numpy.random.default_rng(seed).normal(size=384)`).

### Point Structure

Each point in the collection uses the report's `incident_id` (UUID4 string) as the point ID. The payload is the entire `TriageReport.model_dump()`.

### Similarity Search

`HistoricalLookup.find_similar(log_text, top_k=3)` embeds the query log text, then calls `client.query_points()` with `with_payload=True`. Returns incident_id, severity, and title of top-3 matches.

### Docker Deployment

Run via `scripts/setup_qdrant.sh`:
```bash
docker run -d --name qdrant --restart unless-stopped -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest
```
Health check: `GET http://localhost:6333/healthz`

### Graceful Degradation

If Qdrant is unavailable at startup (`_ensure_collection` fails), `self.qdrant_available` is set to `False` and storage is skipped. The same applies if an `upsert` call fails mid-operation (permanently disables after first failure).

---

## 5. Configuration System

### File: `backend/config/settings.yaml`

```yaml
redis:
  host: localhost
  port: 6379

qdrant:
  host: localhost
  port: 6333
  collection: triage_reports

neurallog:
  window_size: 20
  step_size: 1
  anomaly_threshold: 0.5
  bert_model: bert-base-uncased
  embedding_cache_dir: data/embeddings
  nhead: 2
  num_layers: 2
  dim_feedforward: 512
  dropout: 0.1

embedding:
  report_model: all-MiniLM-L6-v2
  report_dim: 384

llm:
  provider: groq            # groq (primary) or ollama (fallback)
  ollama_model: gemma3:4b
  ollama_base_url: http://localhost:11434
  groq_model: llama-3.1-8b-instant

api:
  nvd_rate_limit_no_key: 5     # requests per 30 seconds
  nvd_rate_limit_with_key: 50

prefilter:
  critical_keywords:
    - CRITICAL
    - EMERGENCY
    - FATAL
  auth_fail_threshold: 5
  auth_fail_window_seconds: 60
  privilege_escalation_patterns:
    - "sudo.*COMMAND=/bin/bash"
    - "sudo.*COMMAND=/bin/sh"
    - "su.*authentication failure"

dashboard:
  fastapi_port: 8000
  nextjs_port: 3000
```

### Environment Variables (`.env`)

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Required for Groq LLM provider |
| `ABUSEIPDB_API_KEY` | Required for IP reputation lookups |
| `NVD_API_KEY` | Optional, increases NVD API rate limit |

### How Config Is Loaded

Each module that needs config loads it independently via:
```python
config_path = Path(__file__).resolve().parents[N] / "config" / "settings.yaml"
```

There is **no shared singleton or dependency injection** for config. Each class (PreFilter, SequenceBuilder, NeuralLogInference, TriageAgent, HistoricalLookup, etc.) parses the YAML file independently.

---

## 6. Stage 1: Log Ingestion & Prefiltering

### Entry Point

```
python -m ingestion.producer [--mode normal|attack] [--rate 10] [--count N] [--file path] [--dataset_dir path]
```

### Synthetic Log Generator

**File**: `backend/ingestion/synthetic_logs.py`

**Function**: `generate_logs(mode, rate, count, sleep, start_time)` → Generator[dict]

- Fixed IP pools: `192.168.1.10-20` (internal), `203.0.113.10-20` (attacker)
- 4 normal templates, 5 attack templates
- `mode="normal"`: 10% attack probability
- `mode="attack"`: 60% attack probability
- Timestamps advance `random.randint(1,5)` seconds per line
- `sleep=True` (default): real-time throttling at `rate` lines/sec
- `sleep=False`: yield as fast as possible (used during training data generation)

**Normal templates**:
1. `Accepted password for {user} from {ip} port {port} ssh2`
2. `CRON[{pid}]: (root) CMD (run-parts /etc/cron.hourly)`
3. `systemd[1]: Started OpenSSH Server Daemon`
4. `pam_unix(sshd:session): session opened for user {user}`

**Attack templates**:
1. `Failed password for invalid user {user} from {ip} port 22 ssh2`
2. `sudo: {user} : TTY=pts/0 ; PWD=/home/{user} ; USER=root ; COMMAND=/bin/bash`
3. `kernel: CRITICAL: memory allocation failure in zone DMA`
4. `Accepted password for root from {ip} port {port} ssh2`
5. `bash[{pid}]: /dev/tcp/{ip}/4444` (reverse shell indicator)

### Rule-Based PreFilter

**File**: `backend/ingestion/prefilter.py`

**Class**: `PreFilter`

**Rules (in order of evaluation)**:

1. **Critical keywords** — exact substring match against `["CRITICAL", "EMERGENCY", "FATAL"]`
   - Reason: `keyword_match:<keyword>`
2. **Privilege escalation** — regex match against 3 patterns (case-insensitive):
   - `sudo.*COMMAND=/bin/bash`
   - `sudo.*COMMAND=/bin/sh`
   - `su.*authentication failure`
   - Reason: `privilege_escalation`
3. **Brute-force detection** — stateful IP-based tracking:
   - Matches `Failed password` (case-insensitive regex)
   - Extracts IP via `from (\d+\.\d+\.\d+\.\d+)`
   - Maintains per-IP rolling window of failure timestamps (`defaultdict(list)`)
   - Prunes entries older than `auth_fail_window_seconds` (60s)
   - Triggers when count > `auth_fail_threshold` (5) → N+1 events needed
   - Reason: `brute_force:<ip>`
4. **Default** — priority `"normal"`, reason `None`

**Statefulness**: The `PreFilter` instance maintains mutable state (failure timestamps by IP) — it is **not** stateless and cannot be horizontally scaled without moving state to Redis.

### Producer

**File**: `backend/ingestion/producer.py`

**Function**: `main()`

1. Parses CLI arguments
2. Loads config, instantiates `PreFilter`, connects to Redis
3. Builds log iterator:
   - `--file`: reads single file line by line (up to `--count` lines)
   - `--dataset_dir`: scans for `HDFS.log` / `BGL.log` in dir and `preprocessed/` subdir
   - No args: generates synthetic logs
4. For each log line:
   - Runs `prefilter.check(line, time.time())`
   - Builds message dict with `log_line`, `timestamp` (UTC ISO), `priority`, `source`, `prefilter_reason`
   - Calls `redis_client.xadd("stream:raw_logs", {k: str(v) for ...})`
5. Logs progress every 100 messages

---

## 7. Stage 2: Preprocessing & Sequence Construction

### Entry Point

```
python -m preprocessing.sequence_builder
```

### Tokenizer

**File**: `backend/preprocessing/sequence_builder.py` (static method `tokenize_log_line`)

```python
def tokenize_log_line(log_line: str) -> list[str]:
    tokens = []
    for raw_token in re.split(r"[\s:,]+", log_line):
        cleaned = re.sub(r"[^A-Za-z]+", "", raw_token).lower()
        if cleaned:
            tokens.append(cleaned)
    return tokens
```

- Splits on whitespace, colon, comma
- Strips non-alpha characters, lowercases
- Discards empty tokens
- This is intentionally **parsing-free** — no log format knowledge needed

### Sequence Builder

**File**: `backend/preprocessing/sequence_builder.py`

**Class**: `SequenceBuilder`

**Constructor**: `__init__(self, window_size, redis_client=None)`
- Creates a `deque(maxlen=window_size)` to hold window entries
- Default `window_size=20` from `config["neurallog"]["window_size"]`

**Method**: `ingest(fields: Mapping[str, str]) -> tuple[str, dict] | None`
1. Extracts `log_line`, `priority`, `timestamp`, `source` from the raw stream message
2. Tokenizes the log line and appends `{tokens, raw_line, priority, timestamp}` to the deque
3. If deque < `window_size`, returns `None` (window not yet full)
4. Once full, calls `choose_stream(window_entries)` and `build_sequence_payload(window_entries, source)`

**Method**: `publish(stream_name, payload)`
- JSON-encodes nested `sequence` and `raw_lines` fields
- Calls `redis_client.xadd(stream_name, encoded_payload)`

### Router

**File**: `backend/queue/router.py`

**Function**: `choose_stream(window)`
- If **any** entry in the window has `priority == "critical"`, routes to `stream:queue_b`
- Otherwise routes to `stream:queue_a`

**Function**: `build_sequence_payload(window, source)`
- Returns dict with:
  - `sequence`: list of token lists `[["accepted", "password", ...], ["cron", ...], ...]`
  - `raw_lines`: list of original log strings
  - `priority`: `"critical"` if any entry is critical, else `"normal"`
  - `window_start_ts`: timestamp of first entry
  - `window_end_ts`: timestamp of last entry
  - `source`: passthrough

**Function**: `encode_stream_payload(payload)`
- JSON-serializes `sequence` and `raw_lines` (since Redis Streams values must be strings)
- All other fields are `str()` cast

### Main Loop (`main()`)

1. Loads config, connects to Redis, calls `setup_consumer_groups()`
2. Creates `SequenceBuilder(window_size=20)`
3. Infinite `while True` loop:
   - `XREADGROUP(group:preprocessing, sequence_builder, stream:raw_logs, count=10, block=1000ms)`
   - For each message: `ingest()` → if result, `publish()` + `XACK`
   - Exception handling with `logger.exception`; message always acknowledged in `finally`

### Dataset Loaders

#### HDFS Loader

**File**: `backend/preprocessing/dataset_loaders/hdfs_loader.py`

- Groups log lines by `blk_<id>` (regex `blk_[A-Za-z0-9-]+`)
- Loads labels from `anomaly_label.csv` (standard HDFS dataset format)
- Labels: `1/anomaly/anomalous/abnormal/true/yes` → anomaly, `0/normal/norm/false/no` → normal
- Each yielded sequence contains ALL lines for a block ID (variable-length, not fixed window)
- Includes `block_id` in the yielded dict

#### BGL Loader

**File**: `backend/preprocessing/dataset_loaders/bgl_loader.py`

- Reads lines chronologically
- Applies a sliding window (default `window_size=20`, `step_size=1`)
- Lines starting with `-` are normal; everything else is anomalous (BGL convention)
- A window is anomalous if **any** line in it is anomalous
- Yields fixed-length window sequences

#### AIT Loader (Stub)

**File**: `backend/preprocessing/dataset_loaders/ait_loader.py`

```python
raise NotImplementedError("AIT-LDS loader not yet implemented. Reserved for transfer learning stretch goal.")
```

Reserved for future transfer learning work with the AIT-LDS v2.0 dataset (DOI 10.5281/zenodo.5789064).

---

## 8. Stage 3: Anomaly Detection (NeuralLog)

### NeuralLog Model Architecture

**File**: `backend/detection/neurallog/model.py`

```
BERT embeddings (768-dim)
        │
        ▼
┌───────────────────────┐
│  Transformer Encoder  │  nhead=2, num_layers=2, dim_feedforward=512
│  (nn.TransformerEncoder)│
└─────────┬─────────────┘
          │
    Mean Pooling (with padding mask handling)
          │
          ▼
┌───────────────────────┐
│  Linear(768 → 1)      │   Binary classifier (logit output)
└───────────────────────┘
```

**Details**:
- `input_dim=768` (BERT base output dimension)
- `TransformerEncoderLayer`: `batch_first=True`, `activation="gelu"`, `dropout=0.1`
- Pooling: if no padding mask → `mean(dim=1)`; if padding mask → masked mean (sum over valid positions / count of valid positions)
- Classifier: single `nn.Linear(768, 1)` producing logits
- Loss: `BCEWithLogitsLoss` (handles sigmoid internally)

### BERT Embedder

**File**: `backend/detection/neurallog/embeddings.py`

**Class**: `BERTEmbedder`

- Model: `bert-base-uncased` (from HuggingFace transformers)
- **Two execution paths**:
  1. **BERT path** (normal): Loads model with `local_files_only=True`. Tokenizes text as `" ".join(tokens)`, truncates to max_length=128, no padding. Returns CLS token embedding (768-dim) from `outputs.last_hidden_state[:, 0, :]`.
  2. **Fallback path**: If BERT is unavailable (cached model not found), uses a **deterministic pseudo-random embedding** — `hashlib.md5` of joined text as seed, `numpy.random.default_rng(seed).normal(loc=0, scale=1, size=768)`. This allows offline/air-gapped usage.
- **On-disk caching**: Embeddings are cached as `.npy` files in `data/embeddings/` keyed by `md5(" ".join(tokens))`. The `_cache_path` method generates the path; `embed()` checks cache first.
- **Thread safety**: Not guaranteed — filesystem cache race is possible.

### Training Pipeline

**File**: `backend/detection/neurallog/train.py`

**Entry**: `python -m detection.neurallog.train --dataset synthetic|hdfs|bgl --epochs 10 --synthetic_count 5000 --output path --max_lines N`

#### Data Collection

- `--dataset synthetic` → `_sequences_from_synthetic(count, window_size)`:
  1. Generates `count/2` normal logs, then `count/2` attack logs (no sleep)
  2. Builds sliding windows of `window_size` (default 20)
  3. Labels: first half `0` (normal), second half `1` (anomaly)
- `--dataset hdfs` → `HDFSLoader().load_sequences("data/raw", max_lines)`
- `--dataset bgl` → `BGLLoader().load_sequences("data/raw", max_lines)`

#### Split Strategy

**Chronological split**: `train[:80%], test[80%:]` — ensures no future leakage.

#### Embedding

- All sequences are embedded via `BERTEmbedder` before training
- Padded to `max_len` across the dataset (768-dim vectors, zero-padded)
- Padding mask is created (`True` = padding position)
- Labels are `float32` tensors (binary)

#### Training Loop

- `DataLoader`: batch_size=8, shuffle=True (train only)
- `NeuralLog` model with config params (nhead=2, num_layers=2, etc.)
- `BCEWithLogitsLoss` with **positive class weighting**: `pos_weight = negatives / positives` (handles class imbalance)
- `Adam` optimizer: `lr=1e-4`
- Per epoch: train → evaluate (F1, precision, recall on test set)
- Sigmoid threshold for evaluation: `0.5`

#### Checkpoint

Saved via `torch.save({"model_state_dict": ..., "config": ...}, path)`. Default paths:
- synthetic → `data/models/neurallog.pt`
- hdfs → `data/models/neurallog_hdfs.pt`
- bgl → `data/models/neurallog_bgl.pt`

### Inference

**File**: `backend/detection/neurallog/inference.py`

**Class**: `NeuralLogInference`

- Loads checkpoint from path, moves model to `cuda` if available
- `predict(sequence: list[list[str]])`:
  1. Embeds each token list via `BERTEmbedder.embed()` (uses cache)
  2. Pads to a batch of 1 (shape: `[1, seq_len, 768]`)
  3. Forward pass → sigmoid → compare with `anomaly_threshold` (default 0.5)
  4. Returns `{"label": "anomalous"|"normal", "score": float}`

### Queue A Worker

**File**: `backend/queue/queue_a_worker.py`

**Entry**: `python -m queue.queue_a_worker --model-path data/models/neurallog.pt`

1. Sets up consumer groups, connects to Redis, loads NeuralLog inference
2. Infinite loop: `XREADGROUP(group:queue_a, queue_a_worker, stream:queue_a, count=5, block=2000ms)`
3. For each message:
   - JSON-decodes `sequence` and `raw_lines`
   - Runs `inference.predict(sequence)`
   - If `label == "anomalous"`: publishes to `stream:queue_b_escalated` with `detection_source="neurallog_queue_a"`
   - If `label == "normal"`: publishes to `stream:results_normal`
   - Always acknowledges (`XACK`)

### Queue B Worker

**File**: `backend/queue/queue_b_worker.py`

**Entry**: `python -m queue.queue_b_worker --model-path data/models/neurallog.pt`

1. Sets up consumer groups, connects to Redis, loads NeuralLog inference, creates `TriageAgent`
2. Infinite loop: `XREADGROUP(group:queue_b, queue_b_worker, {stream:queue_b: ">", stream:queue_b_escalated: ">"}, count=5, block=2000ms)`
3. For each message:
   - Determines `detection_source`:
     - From `stream:queue_b` → runs inference → `detection_source="prefilter"`
     - From `stream:queue_b_escalated` → reads `anomaly_score` from fields → `detection_source="neurallog_queue_a"`
   - Normalizes message with sequence, raw_lines, anomaly_score, priority, source, detection_source
   - Calls `triage_agent.run(message)`
   - Always acknowledges

---

## 9. Stage 4: LLM Triage & Report Storage

### Triage Report Schema

**File**: `backend/triage/report_schema.py`

```python
class IPReputation(BaseModel):
    ip: str
    abuse_score: int          # AbuseIPDB confidence score (0-100)
    country: str
    isp: str
    total_reports: int

class MITREAttack(BaseModel):
    technique_id: str         # e.g., "T1110"
    technique_name: str       # e.g., "Brute Force"
    tactic: str               # e.g., "Credential Access"
    description: str

class TriageReport(BaseModel):
    incident_id: str                  # UUID4
    timestamp: str                    # UTC ISO datetime
    severity: Literal["Critical", "High", "Medium", "Low", "Informational"]
    title: str
    affected_host: str
    log_source: str                   # "synthetic", "hdfs", "bgl", etc.
    anomaly_score: float
    description: str
    evidence: list[str]               # Raw log lines
    cve_references: list[str]         # CVE IDs
    ip_reputation: Optional[IPReputation]
    mitre_attack: Optional[MITREAttack]
    remediation_steps: list[str]
    similar_past_incidents: list[str] # Incident IDs of past matches
    detection_source: str             # "prefilter" | "neurallog_queue_a"
```

### Triage Agent

**File**: `backend/triage/agent.py`

**Class**: `TriageAgent`

#### Initialization

1. Loads config from `settings.yaml`
2. Instantiates all 4 tools: `MITREMapper`, `CVELookup`, `IPReputationChecker`, `HistoricalLookup`
3. Loads report embedding model (`all-MiniLM-L6-v2`, `local_files_only=True`)
4. Connects to Qdrant, ensures `triage_reports` collection exists
5. Builds LLM:
   - `provider == "groq"`: `ChatGroq(model="llama-3.1-8b-instant", api_key=from_env)`
   - `provider == "ollama"`: `ChatOllama(model="gemma3:4b", base_url="http://localhost:11434")`
   - If LLM construction fails (missing API key, connection error): `self.llm = None`

#### `run(sequence_message) -> TriageReport` — The Main Pipeline

1. **Extract fields**: raw_lines, anomaly_score, detection_source, log_text (joined raw_lines)
2. **Execute all 4 tools** (no LLM call yet):
   - `self.mitre_mapper.map(raw_lines)` → `MITREAttack | None`
   - `self.ip_checker.extract_public_ip(raw_lines)`, then `self.ip_checker.check(ip)` → `IPReputation | None`
   - `self.cve_lookup.extract_keyword(raw_lines)`, then `self.cve_lookup.lookup(keyword)` → `list[dict]`
   - `self.historical_lookup.find_similar(log_text)` → `list[dict]`
3. **LLM path selection**:
   - If `provider == "groq"` → `_run_groq_react(...)`
   - If `provider == "ollama"` → `_run_ollama_deterministic(...)`
   - Both methods build the prompt via `build_prompt(...)`, invoke LLM with `HumanMessage`, extract JSON from response, and call `_report_from_payload(...)`.
   - **Groq path**: Uses a single-turn prompt (not a true ReAct loop despite the name).
   - **Ollama path**: Same prompt, used as a deterministic fallback.
   - **If LLM is None or invocation fails**: `_fallback_report(...)` is returned.
4. **Post-LLM enrichment**: Sets `affected_host`, `log_source`, `anomaly_score`, `detection_source`, `evidence`, `mitre_attack`, `ip_reputation`, `cve_references`, `similar_past_incidents` from tool results (overrides LLM output where applicable).
5. **Store**: `_store_report(report)` → upsert to Qdrant + `xadd` to `stream:triage_reports`
6. Returns `TriageReport`

#### LLM Interaction Detail

Both Groq and Ollama paths follow identical logic:
```python
prompt = build_prompt(raw_lines, anomaly_score, detection_source, mitre_result, ip_result, cve_results, similar_incidents)
response = self.llm.invoke([HumanMessage(content=prompt)])
content = response.content
report_json = self._extract_json(content)  # Strip markdown fences, extract first JSON object
return self._report_from_payload(report_json, raw_lines, anomaly_score, detection_source)
```

#### JSON Extraction (`_extract_json`)

```python
def _extract_json(self, content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`\n")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise
```

#### Report Normalization (`_report_from_payload`)

- Merges LLM output with fallback payload (LLM values take precedence over non-None)
- Normalizes severity to allowed Literal values
- Normalizes IPReputation and MITREAttack to pydantic models (or None)
- Falls through to `_fallback_report_payload` for any missing fields

#### Fallback Report

When LLM is unavailable or fails:
```python
{
    "incident_id": uuid4(),
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "severity": "Low",
    "title": "LLM triage failed",
    "description": "LLM triage failed -- manual review required",
    "remediation_steps": ["Review the alert manually."],
    # Other fields from tools (anomaly_score, evidence, detection_source, mitre_attack, etc.)
}
```

#### Host Extraction

```python
def _extract_host(self, raw_lines: list[str]) -> str:
    first_line = raw_lines[0]
    parts = first_line.split()
    if len(parts) >= 2:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", parts[0]):
            return parts[1].rstrip(":")
        return parts[0].rstrip(":")
    return "unknown"
```

### Triage Prompt

**File**: `backend/triage/prompts/triage_prompt.py`

**Function**: `build_prompt(...)`

Template:
```
You are a SOC analyst assistant.

Evidence:
- <line1>
- <line2>
...

Anomaly score: <float>
Detection source: <string>

MITRE match: <serialized MITREAttack | None>
IP reputation: <serialized IPReputation | None>
CVE results: <list of dicts>
Similar incidents: <list of dicts>

Severity rules:
- Critical: active exploitation, privilege escalation success, reverse shell indicator
- High: brute force with successful login, known malware pattern
- Medium: brute force without successful login, port scanning
- Low: single failed login, anomalous but low-confidence
- Informational: anomaly score triggered but no clear threat

Output ONLY the JSON object. No markdown. No explanation. No code fences.
```

The prompt expects the LLM to return a JSON object matching the `TriageReport` schema.

### Tool Implementations

#### MITRE Mapper

**File**: `backend/triage/tools/mitre_mapper.py`

**Data**: `data/mitre/techniques.json` — 20 MITRE ATT&CK techniques encoded with:
- `technique_id`, `technique_name`, `tactic`, `description`
- `keywords`: list of substring patterns to match against raw log text

**Algorithm**: `_score_technique(joined_text, technique)` counts how many keywords appear as substrings. Returns the technique with the highest count. If no keywords match, returns `None`.

**Example techniques**: T1110 (Brute Force), T1021.004 (SSH Remote Services), T1548.003 (Sudo/Su), T1059.004 (Unix Shell), T1190 (Exploit Public-Facing App), T1105 (Ingress Tool Transfer), T1078 (Valid Accounts), T1053.003 (Cron), T1070.002 (Clear Logs), etc.

#### CVE Lookup

**File**: `backend/triage/tools/cve_lookup.py`

**Data source**: NVD API 2.0 (`https://services.nvd.nist.gov/rest/json/cves/2.0`)

**Keyword extraction**: Regex `\b(sshd|apache|nginx|mysql|php|openssh)\b` from log lines

**API request**: `GET /rest/json/cves/2.0?keywordSearch=<keyword>&resultsPerPage=3` (with optional `apiKey`)

**Response parsing**: Extracts `cve_id`, `description` (English), `cvss_score` (prefers V31 > V30 > V2). Returns up to 3 results.

**Error handling**: Returns empty list on any exception (connection error, timeout, parse error).

#### IP Reputation Checker

**File**: `backend/triage/tools/ip_reputation.py`

**Data source**: AbuseIPDB API v2

**IP extraction**: Regex `\b(\d{1,3}(?:\.\d{1,3}){3})\b`, filters out private IPs:
- `10.x.x.x`, `192.168.x.x`, `172.16-31.x.x`, `127.x.x.x`
- Returns the **first** public IP found (uses regex `re.findall`)

**API request**: `GET https://api.abuseipdb.com/api/v2/check?ipAddress=<ip>&maxAgeInDays=90` with `Key` header

**Response**: Returns `IPReputation(ip, abuseConfidenceScore, countryCode, isp, totalReports)`.

**No-key behavior**: If `ABUSEIPDB_API_KEY` is not set, logs a warning and returns `None`.

**Also provides**: `extract_public_ip_from_text(log_text)` static method for external use.

#### Historical Lookup

**File**: `backend/triage/tools/historical_lookup.py`

**Data source**: Qdrant collection `triage_reports`

**Embedding model**: Same as report storage: `all-MiniLM-L6-v2` (or deterministic fallback)

**Method**: `find_similar(log_text, top_k=3)`
1. Embeds `log_text` using `_embed(text)` (same deterministic fallback as TriageAgent)
2. `client.query_points(collection_name="triage_reports", query=vector, limit=3, with_payload=True)`
3. Returns list of `{incident_id, severity, title}` from top-3 points

**Error handling**: Returns empty list on any exception (Qdrant unavailable, query failure).

**Also provides**: `store_report(report, embedding)` method (functionally equivalent to TriageAgent's upsert, but TriageAgent uses its own code path).

### Storage Flow

Both storage destinations are attempted independently:

1. **Qdrant**: `client.upsert(collection_name="triage_reports", points=[PointStruct(id=incident_id, vector=embedding, payload=report.model_dump())])`
   - Embedding derived from `f"{title} {description} {' '.join(remediation_steps)}"`
   - Falls back to deterministic if sentence-transformers unavailable
   - If Qdrant fails at any point, `self.qdrant_available = False` permanently
2. **Redis Stream**: `client.xadd("stream:triage_reports", {"report": report.model_dump_json()})`
   - Does not disable on failure, just logs warning

---

## 10. Stage 5: Dashboard (Not Started)

All files are **empty (0 bytes)**:

| File | Purpose |
|------|---------|
| `backend/dashboard/main.py` | FastAPI application entry point |
| `backend/dashboard/routes/alerts.py` | REST endpoints for fetching triage reports |
| `backend/dashboard/routes/ws.py` | WebSocket endpoint for real-time alert feed |
| `backend/dashboard/services/qdrant_service.py` | Qdrant query service for dashboard |

**Intended design** (from config):
- FastAPI on port 8000
- Next.js frontend on port 3000
- Frontend would consume alerts via REST + WebSocket
- Qdrant queries for historical search and similarity
- Redis consumer group `group:dashboard` reads `stream:triage_reports` and `stream:results_normal`

---

## 11. Evaluation Package (Not Started)

All files are **empty (0 bytes)**:

| File | Purpose |
|------|---------|
| `backend/evaluation/metrics.py` | Evaluation metrics for anomaly detection |
| `backend/evaluation/benchmark.py` | Benchmarking suite |
| `backend/evaluation/transfer_experiment.py` | Cross-dataset transfer learning experiments |

---

## 12. DeepLog Baseline (Stub)

All three files raise `NotImplementedError`:

| File | Contents |
|------|----------|
| `backend/detection/deeplog/model.py` | `class DeepLog(nn.Module): forward() → NotImplementedError` |
| `backend/detection/deeplog/train.py` | `def main() → NotImplementedError` |
| `backend/detection/deeplog/inference.py` | `def main() → NotImplementedError` |

Planned as a future baseline comparison against NeuralLog. The DeepLog approach treats log messages as event keys and predicts the next key (Du et al. 2017 CCS).

---

## 13. Frontend Application

### Status: Scaffolding Only

**Configuration files**: `package.json`, `next.config.ts`, `tsconfig.json`, `eslint.config.mjs`, `postcss.config.mjs`
**Pages**: `layout.tsx` (root layout with Geist fonts), `page.tsx` (default Next.js starter page)

The frontend is a vanilla `create-next-app` installation with no SOC-specific UI implemented.

### Technology

- Next.js 16.2.3 (App Router)
- React 19.2.4
- TypeScript 5.x
- Tailwind CSS v4 (via `@tailwindcss/postcss`)
- ESLint with `eslint-config-next`

### Notes

- `AGENTS.md` warns that this is a breaking-change version of Next.js — developers are instructed to consult `node_modules/next/dist/docs/`
- `CLAUDE.md` references `AGENTS.md` for implementation guidance

---

## 14. CI/CD Pipeline

### File: `.github/workflows/ci.yml`

**Triggers**: pushes and PRs to `main`

**Backend job** (`backend-check`):
- Ubuntu latest, Python via `uv` (astral-sh/setup-uv@v5)
- `uv python install` → `uv sync` → lint with `ruff` (continue-on-error) → `pytest tests/` (continue-on-error)

**Frontend job** (`frontend-check`):
- Node 20, npm cache
- `npm ci` → `npm run lint` → `npm run build`

Note: Both testing and linting have `continue-on-error: true`, meaning CI will not block merges even if linting or tests fail.

---

## 15. Scripts & Automation

### Setup Scripts

| Script | Purpose |
|--------|---------|
| `scripts/setup.sh` | OS-detection dispatcher → delegates to setup_ubuntu.sh or setup_macos.sh |
| `scripts/setup_ubuntu.sh` | Installs tmux, redis-server, uv, Docker + Qdrant. Enables/starts Redis. |
| `scripts/setup_macos.sh` | macOS equivalent (uses brew) |
| `scripts/setup_qdrant.sh` | Starts Qdrant Docker container (creates if not exists), waits for health |
| `scripts/setup_redis.sh` | **EMPTY** — Redis setup is handled inline by other scripts |

### Pipeline Scripts

| Script | Purpose |
|--------|---------|
| `scripts/run_pipeline.sh` | Synthetic pipeline: trains model if needed, starts tmux session with 4 windows (redis, sequence_builder, queue_a_worker, queue_b_worker, producer). Deletes existing streams first. |
| `scripts/run_real_pipeline.sh` | Real-data pipeline: trains on HDFS or BGL, starts tmux with same windows. Usage: `./run_real_pipeline.sh [hdfs|bgl] [count]` |
| `scripts/cleanup.sh` | Kills tmux session, deletes streams (or `--full` to FLUSHDB), removes model checkpoints and embedding cache |
| `scripts/download_datasets.sh` | Downloads HDFS and BGL datasets from Zenodo (Loghub), extracts to `data/raw/` |

### Pipeline Orchestration via tmux

Both pipeline scripts use the same tmux structure:
1. Window 0: `redis` (starts or confirms Redis)
2. Window 1: `sequence_builder` (waits for Redis, then runs)
3. Window 2: `queue_a_worker` (waits for Redis)
4. Window 3: `queue_b_worker` (waits for Redis)
5. Window 4: `producer` (generates or replays logs)
- `remain-on-exit` is set for the session
- All stdout/stderr are tee'd to `logs/*.log`
- Error trap at `line ${LINENO}: ${BASH_COMMAND}`

---

## 16. Data Flow Walkthrough

### Synthetic Attack Scenario

1. **Producer** (`--mode attack --rate 2 --count 80`):
   - Generates ~60% attack lines
   - PreFilter catches: `CRITICAL` keyword, `sudo` privilege escalation, brute-force patterns
   - Publishes `{priority: "critical", prefilter_reason: "keyword_match:CRITICAL"}` to `stream:raw_logs`

2. **SequenceBuilder** (consuming each message):
   - Tokenizes each line
   - When window reaches 20 entries, calls `choose_stream()`
   - If any line is critical → routes to `stream:queue_b`

3. **QueueBWorker** (consuming from `stream:queue_b`):
   - Runs NeuralLog inference on the window → `{"label": "anomalous", "score": 0.89}`
   - `detection_source = "prefilter"`
   - Calls `triage_agent.run({...})`

4. **TriageAgent**:
   - **MITRE mapper**: matches `T1110 Brute Force` (keywords: "failed password")
   - **IP reputation**: extracts `203.0.113.15` → queries AbuseIPDB → returns `IPReputation(abuse_score=85, ...)`
   - **CVE lookup**: extracts "sshd" → queries NVD → returns CVEs for OpenSSH
   - **Historical lookup**: embeds log text → queries Qdrant → returns similar past incidents
   - **LLM**: Groq generates JSON report with severity "High", title "SSH Brute Force Attack", remediation steps
   - **Storage**: upserts to Qdrant, publishes to `stream:triage_reports`

### Normal Traffic Scenario

1. **Producer** (`--mode normal`): 90% normal lines, 10% attack
2. **SequenceBuilder**: window has no critical lines → routes to `stream:queue_a`
3. **QueueAWorker**: NeuralLog scores as normal (`score < 0.5`) → publishes to `stream:results_normal`
4. **No triage needed**

### Dataset Replay Scenario

1. `run_real_pipeline.sh hdfs 1000` trains on HDFS (1 epoch, 1000 lines)
2. **Producer** (`--file data/raw/HDFS.log --count 1000`): reads HDFS.log line by line
3. Each line is classified by PreFilter (rule-based only, since HDFS logs don't follow SSH patterns)
4. Windows route through QueueA → NeuralLog anomaly detection
5. Escalated anomalies go to TriageAgent

### Failure Scenarios

| Failure | Behavior |
|---------|----------|
| LLM unavailable (no API key) | Falls back to `_fallback_report()`: severity "Low", title "LLM triage failed" |
| Qdrant unavailable | `qdrant_available = False` → storage skipped. HistoricalLookup returns empty list. |
| BERT model unavailable | Deterministic pseudo-random embeddings (consistent via md5 seed) |
| Redis unavailable | Each component crashes on connection (no retry in main.py — pipeline scripts retry via `until redis-cli PING`) |
| AbuseIPDB/NVD API down | Returns None / empty list with warning log |
| Producer with no args | Generates synthetic logs indefinitely (no `--count` → infinite stream) |

---

## 17. Known Gaps & Future Work

### Critical Gaps

1. **No tests exist**: The `tests/` directory is absent from the repository. CI runs `pytest tests/` with `|| echo "No tests found"`. There are zero automated tests for any component.
2. **STAGES.md is outdated**: Stage 4 items 1-6 are checked off but they show as unchecked (the file says `[ ]`). The LLM triage path has no verification that the Groq or Ollama paths actually work end-to-end.
3. **Dashboard not implemented**: Stage 5 (FastAPI + Next.js) is entirely scaffolding. Users cannot view triage reports.
4. **Evaluation not implemented**: No metrics, benchmarks, or transfer experiments exist.
5. **Config loaded redundantly**: Each module loads and parses `settings.yaml` independently — no dependency injection, no shared config object, no validation.
6. **No authentication/authorization**: The dashboard API (future) has no auth. The `.env` file with real API keys is committed to git (though `.gitignore` should now prevent future leaks).
7. **No graceful shutdown**: Workers run infinite `while True` loops with no signal handling. tmux kill is the only stop mechanism.

### Architectural Concerns

1. **PreFilter is stateful**: Brute-force detection stores mutable per-IP failure timestamps in-memory. Horizontal scaling would require moving this state to Redis.
2. **Queue `__init__.py` shadows stdlib**: The `backend/queue/__init__.py` re-exports stdlib `queue` classes (Queue, LifoQueue, PriorityQueue, etc.) using a `_load_stdlib_queue()` hack to avoid shadowing issues. This is fragile.
3. **`qdrant_available` is a mutable boolean flag**: Once Qdrant fails, it's permanently disabled for the worker's lifetime — even if Qdrant recovers.
4. **No idempotency**: Redis Streams use at-least-once delivery. If a worker crashes after processing but before `XACK`, the message is re-delivered. The system has no deduplication mechanism.
5. **LLM prompt is not a true ReAct loop**: Despite being named `_run_groq_react`, the Groq path is a single-turn prompt. There's no tool-calling loop or multi-step reasoning.
6. **Synthetic data leakage**: The synthetic training generator labels windows chronologically (first 50% normal, last 50% attack). This creates an artificial temporal boundary that won't generalize — a real reversal of traffic patterns would misclassify.
7. **BERT fallback is deterministic but not semantically meaningful**: The `md5 → numpy.random` fallback produces consistent but meaningless embeddings. The model would learn noise, not semantics, if trained with this fallback active.

### Feature Gaps

1. **DeepLog baseline**: Not implemented (stub only). No comparison benchmark exists.
2. **AIT-LDS dataset loader**: Stub only (reserved for transfer learning).
3. **No alert deduplication/aggregation**: Each window produces a separate triage report.
4. **No notification system**: No email, Slack, PagerDuty, or webhook integration.
5. **No alert lifecycle management**: No acknowledge, resolve, or suppress states.
6. **No RBAC or multi-tenant support**.
7. **No log rotation for pipeline logs**: `logs/` directory grows unbounded.
8. **No health check endpoints**: No way to monitor pipeline health externally.
9. **No metric export**: No Prometheus/OpenTelemetry integration.

### Maintenance Items

1. **Config files need a schema**: No validation that `settings.yaml` has all required keys.
2. **`ruff` linting not enforced**: CI has `continue-on-error: true` for linting.
3. **`.env` was committed**: Real API keys for Groq and AbuseIPDB are in git history.
4. **Bash-specific syntax**: Scripts use `set -Eeuo pipefail` which is bash 4+ only (not POSIX sh). The macOS script notably uses bash 3.2 which lacks `pipefail` — this was a known bug fixed via PR merge.
5. **`setup_redis.sh` is empty**: Redis setup is duplicated across setup_ubuntu.sh and run_pipeline.sh.

---

## 18. Security Considerations

### Current Issues

1. **API keys in git**: `.env` with `GROQ_API_KEY` and `ABUSEIPDB_API_KEY` was committed. The `.env` is now in `.gitignore`, but the keys remain in git history.
2. **No input validation**: Log lines from producers are forwarded through the pipeline without sanitization.
3. **No rate limiting**: Producers can flood Redis. NVD rate limits are noted in config but not enforced in code.
4. **No TLS**: Redis, Qdrant, and the dashboard API all communicate over plain TCP/HTTP.
5. **No authentication**: Anyone who can reach port 6379 or 6333 can read/write Redis/Qdrant.

### Mitigations Present

1. **Deterministic fallback for embeddings**: Allows offline operation without data exfiltration.
2. **Graceful degradation**: The system degrades rather than crashes when external services are unavailable.
3. **Consumer group acknowledgment in `finally`**: Ensures messages are always acknowledged even on error (at-least-once delivery).
