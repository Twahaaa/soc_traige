# Claude Code Prompt: SOC Triage MVP Pipeline

---

## WHO YOU ARE AND WHAT YOU ARE BUILDING

You are building the backend pipeline for a university major project: a real-time security log
anomaly detection and LLM-based incident triage system. The architecture is fully finalized.
You are not making design decisions -- you are implementing what is specified here.

The GitHub repo is at: https://github.com/Twahaaa/soc_traige
The repo already has a `backend/` and `frontend/` directory. All work in this session goes
inside `backend/`. Do not touch the frontend directory.

The pipeline has five stages:
1. Log ingestion and pre-filtering
2. Preprocessing and sequence construction (parsing-free -- no Drain, no template extraction)
3. Anomaly detection (NeuralLog primary, DeepLog baseline)
4. LLM triage report generation (LangChain agent + 4 tools)
5. Report storage in Qdrant

This session covers stages 1 through 4. Stage 5 (Qdrant storage) is included as part of
stage 4. The dashboard (FastAPI + Next.js) is out of scope for this session.

---

## CRITICAL RULES -- READ BEFORE WRITING ANY CODE

1. **Build one stage at a time.** Do not start stage 2 until stage 1 is complete and verified.
   After completing each stage, stop. Explain what you built, how to test it, what the
   expected output looks like, and what can go wrong. Wait for confirmation before continuing.

2. **No placeholder functions.** Every function must be fully implemented. If a dependency
   from a later stage is needed, use a realistic mock that returns the correct data shape.

3. **Use `uv` for all package management.** Do not use pip. Before adding any dependency,
   list every package and a one-line reason why it is needed. Use `uv add <package>` to
   install. The project uses `pyproject.toml` for dependency management, not requirements.txt.

4. **Groq is the default LLM provider.** The Groq API key is available via the
   `GROQ_API_KEY` environment variable. Default LLM backend is Groq (remote, Llama 3).
   Ollama is the local fallback for when Groq rate limits are hit. Both paths must be
   fully implemented:
   - Groq path: LangChain ReAct agent where the LLM decides which tools to call.
   - Ollama path: deterministic -- all 4 tools are called before the LLM, results injected
     into the prompt. Small local models (4B-7B) are unreliable at function calling.
   The provider is configurable in `config/settings.yaml` (`llm.provider: groq | ollama`).

5. **Datasets: HDFS and BGL are the primary datasets.** Use the synthetic log generator
   for initial pipeline testing. Implement `scripts/download_datasets.sh` to download
   HDFS and BGL from Loghub (Zenodo). Implement the dataset loaders (`hdfs_loader.py`,
   `bgl_loader.py`) fully -- these are not stubs. `ait_loader.py` is a stub for future
   transfer learning work.

6. **Respect the directory structure exactly.** It is specified below. Do not invent new
   files or reorganize.

7. **All config lives in `config/settings.yaml`.** No hardcoded values anywhere in code.
   API keys and secrets are loaded from environment variables (use `python-dotenv`).
   Create a `.env.example` file listing all required environment variables.

8. **Write clean, commented code.** Teammates are still learning. Every non-obvious block
   of logic needs a comment explaining what it does and why.

9. **Python 3.11+ required.** Use type hints on all function signatures. Use Pydantic
   for all data schemas. Use `async/await` for FastAPI handlers and Redis operations
   where possible.

10. **NeuralLog is parsing-free.** There is no Drain parser, no log template extraction,
    no log key sequence construction. NeuralLog takes raw tokenized log messages, embeds
    them with BERT (`bert-base-uncased`), and feeds the embeddings into a Transformer
    encoder. The preprocessing is minimal: tokenize, lowercase, remove non-alphabetic
    tokens. This is a deliberate architectural choice -- do not add a parsing step.

11. **Two separate embedding models exist in this project. Do not confuse them.**
    - `bert-base-uncased` (768-dim): used INSIDE NeuralLog for log message representation
      during anomaly detection. Managed by `detection/neurallog/embeddings.py`.
    - `all-MiniLM-L6-v2` (384-dim): used for embedding triage reports for Qdrant vector
      similarity search. Managed by `triage/tools/historical_lookup.py`.
    These models serve completely different purposes and do not interact.

12. **Logging configuration.** Use Python's `logging` module. Configure a root logger in
    each entry point script with format:
    `"%(asctime)s [%(name)s] %(levelname)s: %(message)s"`. Default level: INFO.

---

## DIRECTORY STRUCTURE

Create the following inside `backend/`. Files marked [stub] need their interface defined
but implementation is a TODO for later.

```
backend/
  config/
    settings.yaml
  ingestion/
    __init__.py
    producer.py
    prefilter.py
    synthetic_logs.py
  preprocessing/
    __init__.py
    sequence_builder.py
    dataset_loaders/
      __init__.py
      hdfs_loader.py
      bgl_loader.py
      ait_loader.py         [stub -- future transfer learning]
  detection/
    __init__.py
    neurallog/
      __init__.py
      model.py
      train.py
      inference.py
      embeddings.py
    deeplog/
      __init__.py
      model.py              [stub]
      train.py              [stub]
      inference.py          [stub]
  triage/
    __init__.py
    agent.py
    tools/
      __init__.py
      cve_lookup.py
      ip_reputation.py
      historical_lookup.py
      mitre_mapper.py
    prompts/
      __init__.py
      triage_prompt.py
    report_schema.py
  queue/
    __init__.py
    redis_manager.py
    queue_a_worker.py
    queue_b_worker.py
    router.py
  data/
    raw/                    # Dataset files (HDFS, BGL) -- gitignored
    embeddings/             # Cached BERT embeddings -- gitignored
    models/                 # Trained model checkpoints -- gitignored
    mitre/
      techniques.json
  scripts/
    setup.sh
    download_datasets.sh    # Downloads HDFS + BGL from Loghub
    run_pipeline.sh
  .env.example
  .gitignore
  pyproject.toml
  README.md
```

---

## .env.example

```
GROQ_API_KEY=your_groq_api_key_here
ABUSEIPDB_API_KEY=your_abuseipdb_key_here
NVD_API_KEY=your_nvd_api_key_here
```

---

## .gitignore

```
data/raw/
data/embeddings/
data/models/
.env
__pycache__/
*.pyc
.venv/
```

---

## config/settings.yaml

Create this first before any code. Everything reads from here.
API keys are loaded from environment variables at runtime, not stored in this file.

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
  # Paper defaults for reference (Le & Zhang, ASE 2021):
  # nhead: 8, num_layers: 6
  # Reduced for development/synthetic training:
  nhead: 2
  num_layers: 2
  dim_feedforward: 512
  dropout: 0.1

embedding:
  report_model: all-MiniLM-L6-v2
  report_dim: 384

llm:
  provider: groq            # groq (default) or ollama (fallback)
  ollama_model: gemma3:4b
  ollama_base_url: http://localhost:11434
  groq_model: llama3-70b-8192
  # groq_api_key loaded from GROQ_API_KEY env var

api:
  # abuseipdb_key loaded from ABUSEIPDB_API_KEY env var
  # nvd_api_key loaded from NVD_API_KEY env var
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

---

## STAGE 1: Log Ingestion

**Goal:** Get synthetic log lines flowing into Redis Stream `stream:raw_logs`. This stage
has no ML -- it is purely I/O and pattern matching.

### `ingestion/synthetic_logs.py`

A generator function `generate_logs(mode="normal", rate=10.0, count=None)`:

- `mode`: `"normal"` or `"attack"`
  - `"normal"`: 90% benign lines, 10% mildly suspicious
  - `"attack"`: 40% benign, 60% attack-pattern lines
- `rate`: lines per second. Use `time.sleep(1/rate)` between yields.
- `count`: total lines. If `None`, run forever.

Each yielded value is a dict: `{"log_line": str, "source_type": "synthetic"}`

Generate realistic Linux syslog/auth.log format. Use random choices from these templates
(substitute realistic values for hostnames, IPs, PIDs, users):

Normal:
```
May 15 10:23:01 server01 sshd[1234]: Accepted password for user1 from 192.168.1.10 port 54321 ssh2
May 15 10:26:00 server01 CRON[5678]: (root) CMD (run-parts /etc/cron.hourly)
May 15 10:27:00 server01 systemd[1]: Started OpenSSH Server Daemon
May 15 10:30:00 server01 sshd[2222]: pam_unix(sshd:session): session opened for user user1
```

Attack/suspicious:
```
May 15 10:23:05 server01 sshd[1235]: Failed password for invalid user admin from 203.0.113.45 port 22 ssh2
May 15 10:24:00 server01 sudo: user1 : TTY=pts/0 ; PWD=/home/user1 ; USER=root ; COMMAND=/bin/bash
May 15 10:25:00 server01 kernel: CRITICAL: memory allocation failure in zone DMA
May 15 10:28:00 server01 sshd[9999]: Accepted password for root from 203.0.113.45 port 44444 ssh2
May 15 10:29:00 server01 bash[3141]: /dev/tcp/203.0.113.45/4444
```

Use a fixed pool of internal IPs (192.168.1.x) for normal traffic and a fixed pool of
attacker IPs (203.0.113.x) for attack traffic so the brute force detector can fire.
Randomize timestamps incrementally (each log is a few seconds after the previous).

### `ingestion/prefilter.py`

Class `PreFilter` initialized with config. Method `check(log_line: str, timestamp: float) -> dict`:

Returns: `{"priority": "critical" | "normal", "reason": str | None}`

Rules checked in order:
1. If any keyword from `critical_keywords` appears in the line: `priority: critical`, reason: `"keyword_match:<keyword>"`
2. If line matches any `privilege_escalation_patterns` regex: `priority: critical`, reason: `"privilege_escalation"`
3. Brute force detection: if line contains `"Failed password"`, extract source IP with
   regex `from (\d+\.\d+\.\d+\.\d+)`, store `(timestamp)` in a `defaultdict(list)` keyed
   by IP. Prune entries older than `auth_fail_window_seconds`. If count exceeds
   `auth_fail_threshold`: `priority: critical`, reason: `"brute_force:<ip>"`

### `ingestion/producer.py`

Entry point: `python -m ingestion.producer [--mode normal|attack] [--rate 10.0] [--count 1000] [--file <path>]`

Behavior:
- If `--file` is given: read file line by line, each line is a log message (for real datasets)
- Otherwise: use `generate_logs(mode, rate, count)`
- For each line:
  1. Apply `PreFilter.check(log_line, time.time())`
  2. Build Redis message:
     ```json
     {
       "log_line": "<string>",
       "timestamp": "<ISO8601>",
       "priority": "critical | normal",
       "source": "synthetic | <filename>",
       "prefilter_reason": "<string | null>"
     }
     ```
  3. `XADD stream:raw_logs * field1 value1 field2 value2 ...`
- Print to stdout every 100 messages:
  `[producer] 100 published | last: <priority> | <first 60 chars of log line>`

### `queue/redis_manager.py`

`get_redis_client()`: returns a connected `redis.Redis` instance from config.

`setup_consumer_groups()`: creates consumer groups. Use `XGROUP CREATE <stream> <group> $ MKSTREAM`.
Catch `ResponseError` if group already exists and continue silently.

Streams and groups to create:
- `stream:raw_logs` -> `group:preprocessing`
- `stream:queue_a` -> `group:queue_a`
- `stream:queue_b` -> `group:queue_b`
- `stream:queue_b_escalated` -> `group:queue_b`
- `stream:results_normal` -> `group:dashboard`
- `stream:triage_reports` -> `group:dashboard`

### Stage 1 verification

After building stage 1, before doing anything else, output:
1. Full list of packages to add with `uv add` and a one-line reason per package
2. Command to start Redis (assume Redis is installed locally)
3. Command to run the producer in attack mode at rate 2
4. Exact redis-cli commands to verify messages are in the stream
5. What a correct raw message looks like when inspected with XRANGE
6. How to confirm the brute force rule fired (what to look for in producer stdout)

**Stop here. Wait for the user to confirm stage 1 works.**

---

## STAGE 2: Preprocessing and Sequence Construction

**Goal:** Consume from `stream:raw_logs`, tokenize log messages, build sliding-window
sequences, route to `stream:queue_a` or `stream:queue_b`.

**Important: NeuralLog is parsing-free.** The preprocessing here is NOT log parsing. There is
no Drain, no template extraction, no log key identification. We are doing minimal text
tokenization so that BERT can embed the log messages. NeuralLog's key innovation is that
it skips the fragile parsing step entirely and uses BERT semantic embeddings directly on
raw (minimally cleaned) log text.

### `preprocessing/sequence_builder.py`

Class `SequenceBuilder`:

**`tokenize(log_line: str) -> list[str]`**:
- Split on whitespace, colon, comma
- Lowercase all tokens
- Keep only tokens containing at least one alphabetic character (drop pure numbers,
  pure punctuation, IP addresses, PIDs)
- This is NeuralLog-specific preprocessing, NOT log parsing
- Example input: `"Failed password for invalid user admin from 203.0.113.45 port 22 ssh2"`
- Example output: `["failed", "password", "for", "invalid", "user", "admin", "from", "port", "ssh"]`

**Sequence buffer:**
- Maintain a `deque(maxlen=window_size)` of dicts: `{"tokens": list[str], "raw_line": str, "priority": str, "timestamp": str}`
- On each new message, append to deque
- When deque reaches `window_size`, emit a sequence

**Routing:**
- If any entry in the window has `priority == "critical"`: publish to `stream:queue_b`
- Otherwise: publish to `stream:queue_a`

**Published message format:**
```json
{
  "sequence": [["token1", "token2"], ["token1", "token2"], ...],
  "raw_lines": ["original log line 1", "original log line 2", ...],
  "priority": "critical | normal",
  "window_start_ts": "<ISO8601>",
  "window_end_ts": "<ISO8601>",
  "source": "synthetic"
}
```

**Consumer loop:** `python -m preprocessing.sequence_builder`

Use `XREADGROUP GROUP group:preprocessing consumer:sequence_builder COUNT 10 BLOCK 1000 STREAMS stream:raw_logs >`.
`XACK` each message after processing. Log routing decisions:
`[preprocessor] window=20 | priority=<priority> -> <queue_a|queue_b>`

### Dataset Loaders (Fully Implemented)

**`hdfs_loader.py`**: Class `HDFSLoader`.

Method `load_sequences(data_dir: str) -> Iterator[dict]`:
- HDFS logs are grouped by block ID. Each block ID (e.g., `blk_123456789`) has a
  sequence of related log events.
- Read the structured HDFS data from Loghub:
  - `HDFS.log` contains the raw log messages
  - `anomaly_label.csv` contains block IDs and their labels (Normal/Anomalous)
- Group log messages by block ID (extract from each log line with regex)
- For each block, build a sequence of tokenized log messages
- Yield dicts matching the sequence format used by the pipeline
- Label: 1 if anomalous block, 0 if normal

**`bgl_loader.py`**: Class `BGLLoader`.

Method `load_sequences(data_dir: str, window_size: int = 20, step_size: int = 1) -> Iterator[dict]`:
- BGL logs are grouped chronologically using a sliding window
- Read `BGL.log` from Loghub
- Each line starts with `-` (normal) or an alert category (anomalous)
- Build sliding windows of size `window_size` with step `step_size`
- Label: 1 if any line in the window is anomalous, 0 if all normal

**`ait_loader.py`**: [STUB -- future transfer learning experiment]
- Class `AITLoader`, per-host per-logfile chronological grouping
- Docstring: Zenodo DOI 10.5281/zenodo.5789064, CC BY-NC-SA 4.0 license
- Body: `raise NotImplementedError("AIT-LDS loader not yet implemented. Reserved for transfer learning stretch goal.")`

### `scripts/download_datasets.sh`

```bash
#!/bin/bash
# Download HDFS and BGL datasets from Loghub (Zenodo)
set -e

DATA_DIR="data/raw"
mkdir -p "$DATA_DIR"

echo "[download] Downloading HDFS dataset..."
if [ ! -f "$DATA_DIR/HDFS.log" ]; then
    wget -P "$DATA_DIR" https://zenodo.org/records/8196385/files/HDFS_v1.zip
    unzip "$DATA_DIR/HDFS_v1.zip" -d "$DATA_DIR/hdfs_tmp"
    mv "$DATA_DIR/hdfs_tmp/"* "$DATA_DIR/"
    rm -rf "$DATA_DIR/hdfs_tmp" "$DATA_DIR/HDFS_v1.zip"
    echo "[download] HDFS dataset ready"
else
    echo "[download] HDFS dataset already exists, skipping"
fi

echo "[download] Downloading BGL dataset..."
if [ ! -f "$DATA_DIR/BGL.log" ]; then
    wget -P "$DATA_DIR" https://zenodo.org/records/8196385/files/BGL.zip
    unzip "$DATA_DIR/BGL.zip" -d "$DATA_DIR/bgl_tmp"
    mv "$DATA_DIR/bgl_tmp/"* "$DATA_DIR/"
    rm -rf "$DATA_DIR/bgl_tmp" "$DATA_DIR/BGL.zip"
    echo "[download] BGL dataset ready"
else
    echo "[download] BGL dataset already exists, skipping"
fi

echo "[download] All datasets ready in $DATA_DIR"
```

**Important:** Verify these Zenodo URLs are correct before running. The Loghub datasets
are hosted at https://github.com/logpai/loghub and mirrored on Zenodo. If URLs have
changed, check https://github.com/logpai/loghub for current download links.

### Stage 2 verification

After building stage 2, output:
1. How to run the sequence builder
2. Redis-cli commands to check `stream:queue_a` and `stream:queue_b` message counts
3. How to confirm attack-mode logs are routing to `stream:queue_b` specifically
4. What a correct sequence message looks like when inspected with XRANGE

**Stop here. Wait for the user to confirm stage 2 works.**

---

## STAGE 3: Anomaly Detection

**Goal:** NeuralLog scores sequences. Anomalous sequences escalate to queue_b for triage.

Build in this order: model -> embeddings -> training -> inference -> queue_a_worker -> queue_b_worker.

### `detection/neurallog/model.py`

NeuralLog architecture from Le and Zhang, ASE 2021 (arXiv:2108.01955):

```python
class NeuralLog(nn.Module):
    """
    NeuralLog: parsing-free log anomaly detection using BERT embeddings + Transformer encoder.

    This model takes pre-computed BERT [CLS] embeddings of log messages as input.
    It does NOT parse logs into templates. It uses BERT's semantic understanding
    of raw log text directly.

    Input: (batch_size, seq_len, 768) -- one 768-dim BERT [CLS] embedding per log message
    Output: (batch_size, 1) -- anomaly probability after sigmoid

    Architecture parameters from the paper:
    - nhead=8, num_layers=6 (production/benchmark config)
    - nhead=2, num_layers=2 (development/synthetic config, set in settings.yaml)
    """
    def __init__(self, input_dim=768, nhead=2, num_layers=2, dim_feedforward=512, dropout=0.1):
        ...
```

Use `nn.TransformerEncoder` with `nn.TransformerEncoderLayer`. After the encoder, take the
mean of all sequence positions, pass through a linear layer (768 -> 1), apply sigmoid.

**Loss function: use `nn.BCEWithLogitsLoss`** (NOT `nn.BCELoss`). `BCEWithLogitsLoss`
supports `pos_weight` for class imbalance handling and is numerically more stable. When
using `BCEWithLogitsLoss`, remove the sigmoid from the model's forward method -- the loss
function applies sigmoid internally. Add sigmoid only during inference (in `inference.py`).

### `detection/neurallog/embeddings.py`

Class `BERTEmbedder`:
- Load `bert-base-uncased` tokenizer and model from HuggingFace at init. Set model to eval mode.
- **This is a different model from `all-MiniLM-L6-v2` used for Qdrant report embeddings.**
- `embed(tokens: list[str]) -> np.ndarray`:
  - Join tokens into a string
  - Hash the joined string with `hashlib.md5` for cache key
  - Check `embedding_cache_dir/<hash>.npy` -- if exists, load and return
  - Otherwise: tokenize with max_length=128, truncation=True, run through BERT,
    take `last_hidden_state[:, 0, :]` (the [CLS] token), detach to numpy
  - Save to cache before returning
  - Shape returned: `(768,)`
- **Cache invalidation note:** If you change the BERT model or tokenizer settings,
  delete the `data/embeddings/` directory to clear stale cached embeddings.

Run inference with `torch.no_grad()`.

### `detection/neurallog/train.py`

`python -m detection.neurallog.train [--dataset synthetic|hdfs|bgl] [--epochs 10] [--synthetic_count 5000] [--output data/models/neurallog.pt]`

**For `--dataset synthetic` (pipeline verification):**
1. Generate `synthetic_count` log lines: first half in `"normal"` mode, second half in `"attack"` mode
2. Build sequences using a sliding window of size `window_size`, step 1, chronologically
3. Label each sequence: 1 if any line in the window came from attack mode, 0 otherwise
4. Chronological 80/20 split -- first 80% of sequences for training, last 20% for test.
   Comment explaining why: random splits leak future patterns into training data, inflating scores.
5. Embed all sequences using `BERTEmbedder` (cache will speed up reruns significantly)
6. Dataset: `torch.utils.data.TensorDataset` of `(embeddings, labels)`
7. Compute `pos_weight` from label distribution for `BCEWithLogitsLoss`
8. Train with `Adam`, learning rate 1e-4, print loss per epoch
9. After each epoch: compute F1, precision, recall on test split using sklearn
10. Save final checkpoint to `--output`
11. Print a summary: `Training complete. Test F1: X.XX | Precision: X.XX | Recall: X.XX`

**For `--dataset hdfs`:**
1. Use `HDFSLoader.load_sequences("data/raw/")` to get labeled sequences
2. Same training pipeline as above but with real data
3. Save checkpoint as `data/models/neurallog_hdfs.pt`

**For `--dataset bgl`:**
1. Use `BGLLoader.load_sequences("data/raw/")` to get labeled sequences
2. Same training pipeline
3. Save checkpoint as `data/models/neurallog_bgl.pt`

### `detection/neurallog/inference.py`

Class `NeuralLogInference`:
- `__init__(model_path: str)`: load checkpoint. Raise a clear error if file does not exist with
  instruction to run the training script first.
- `predict(sequence: list[list[str]]) -> dict`:
  - Embed each token list using `BERTEmbedder`
  - Stack into tensor of shape `(1, seq_len, 768)`
  - Run through `NeuralLog` model
  - **Apply sigmoid here** (since the model outputs logits when using BCEWithLogitsLoss)
  - Return `{"label": "anomalous" | "normal", "score": float}`
  - Threshold from config: if score >= anomaly_threshold -> "anomalous"

### `queue/queue_a_worker.py`

Entry point: `python -m queue.queue_a_worker`

Init: load `NeuralLogInference(model_path)`. If model file not found, exit with error.

Consumer loop using `XREADGROUP GROUP group:queue_a consumer:queue_a_worker COUNT 5 BLOCK 2000 STREAMS stream:queue_a >`:

For each message:
1. Parse the sequence JSON
2. Run `NeuralLogInference.predict(sequence)`
3. If anomalous AND score >= threshold:
   - Publish to `stream:queue_b_escalated`:
     ```json
     {
       "sequence": [...],
       "raw_lines": [...],
       "anomaly_score": 0.87,
       "priority": "normal",
       "detection_source": "neurallog_queue_a",
       "window_start_ts": "...",
       "window_end_ts": "...",
       "source": "synthetic"
     }
     ```
4. Else: publish to `stream:results_normal` with score and label
5. `XACK stream:queue_a group:queue_a <message_id>`
6. Log: `[queue_a] <label> | score=<score:.3f> | <first 60 chars of first raw line>`

### `queue/queue_b_worker.py`

Entry point: `python -m queue.queue_b_worker`

Init: load `NeuralLogInference` (same model as queue_a).

Consumer loop reading from TWO streams simultaneously:
```python
redis_client.xreadgroup(
    groupname="group:queue_b",
    consumername="queue_b_worker",
    streams={"stream:queue_b": ">", "stream:queue_b_escalated": ">"},
    count=5,
    block=2000
)
```

For items from `stream:queue_b` (pre-filter path):
- Run `NeuralLogInference.predict()` to get a score (needed for the report)
- Set `detection_source = "prefilter"`
- Proceed to triage regardless of score

For items from `stream:queue_b_escalated`:
- Score already present in message -- do not re-run inference
- Set `detection_source = "neurallog_queue_a"`

After handling either source: call `TriageAgent.run(message)` (stage 4).
XACK both streams after processing.
Log: `[queue_b] TRIAGE TRIGGERED | source=<detection_source> | score=<score:.3f>`

### DeepLog stubs

`detection/deeplog/model.py`: Class `DeepLog(nn.Module)` with docstring explaining it is an
LSTM that treats log messages as a sequence of event keys and predicts the next key. Forward
raises `NotImplementedError("DeepLog baseline not implemented. See Du et al. 2017 CCS. Implement after NeuralLog is working.")`.

Same stub structure for `train.py` and `inference.py`.

### Stage 3 verification

After building stage 3, output:
1. All packages to add with `uv add` and a one-line reason each
2. Exact command to run synthetic training and what stdout should look like
3. How to run queue_a_worker and queue_b_worker
4. Redis-cli commands to verify escalations are appearing in `stream:queue_b_escalated`
5. What score range to expect from a model trained on synthetic data
6. Common failure modes and how to diagnose them

**Stop here. Wait for the user to confirm stage 3 works.**

---

## STAGE 4: LLM Triage and Qdrant Storage

**Goal:** LangChain agent receives anomalous sequences, calls 4 tools, generates a
structured JSON triage report, stores it in Qdrant.

Two LLM execution paths exist based on `llm.provider` in config:
- **Groq (default):** LangChain ReAct agent. The LLM decides which tools to call via a
  tool-use loop. Use `langchain_groq.ChatGroq` with tool binding.
- **Ollama (fallback):** Deterministic. All 4 tools are called before the LLM is invoked.
  Results are injected directly into the prompt. The LLM only writes the report.

### `triage/report_schema.py`

```python
from pydantic import BaseModel
from typing import Optional

class IPReputation(BaseModel):
    ip: str
    abuse_score: int
    country: str
    isp: str
    total_reports: int

class MITREAttack(BaseModel):
    technique_id: str
    technique_name: str
    tactic: str
    description: str

class TriageReport(BaseModel):
    incident_id: str
    timestamp: str
    severity: str               # Critical | High | Medium | Low | Informational
    title: str
    affected_host: str
    log_source: str
    anomaly_score: float
    description: str
    evidence: list[str]
    cve_references: list[str]
    ip_reputation: Optional[IPReputation]
    mitre_attack: Optional[MITREAttack]
    remediation_steps: list[str]
    similar_past_incidents: list[str]
    detection_source: str
```

### `data/mitre/techniques.json`

A JSON array of 20 entries covering attacks relevant to common Linux security incidents.
Each entry:

```json
{
  "technique_id": "T1110",
  "technique_name": "Brute Force",
  "tactic": "Credential Access",
  "keywords": ["failed password", "authentication failure", "invalid user", "failed login"],
  "description": "Adversaries may use brute force techniques to gain access to accounts when passwords are unknown or when password hashes are obtained."
}
```

Include at minimum: T1110, T1021.004 (SSH Remote Services), T1548.003 (Sudo and Sudo Caching),
T1059.004 (Unix Shell), T1190 (Exploit Public-Facing Application), T1046 (Network Service
Discovery), T1083 (File and Directory Discovery), T1105 (Ingress Tool Transfer), T1071.004
(DNS Application Layer Protocol), T1133 (External Remote Services), T1098 (Account
Manipulation), T1053.003 (Cron), T1070.002 (Clear Linux or Mac System Logs),
T1087.001 (Local Account Discovery), T1049 (System Network Connections Discovery),
T1057 (Process Discovery), T1078 (Valid Accounts), T1136.001 (Create Local Account),
T1547.006 (Kernel Modules), T1014 (Rootkit).

### `triage/tools/mitre_mapper.py`

```python
class MITREMapper:
    def __init__(self, techniques_path="data/mitre/techniques.json"):
        ...  # load JSON at init

    def map(self, log_lines: list[str]) -> Optional[MITREAttack]:
        # Join all log lines, lowercase
        # For each technique, count how many of its keywords appear in the joined text
        # Return the technique with the highest match count (minimum 1 match required)
        # Return None if no technique matches
```

### `triage/tools/cve_lookup.py`

```python
class CVELookup:
    def lookup(self, keyword: str) -> list[dict]:
        # NVD API v2: https://services.nvd.nist.gov/rest/json/cves/2.0
        # Query params: keywordSearch=<keyword>, resultsPerPage=3
        # If NVD_API_KEY env var is set: add apiKey param
        # Return list of {"cve_id": str, "description": str, "cvss_score": float|None}
        # On any failure (network, rate limit, parse error): return [] and log warning
        # Do NOT crash the pipeline
```

Extract a keyword from the log sequence before calling: look for known software names
(sshd, apache, nginx, mysql, php, openssh) by regex. If none found, skip the CVE lookup
and return empty list.

### `triage/tools/ip_reputation.py`

```python
class IPReputationChecker:
    def check(self, ip: str) -> Optional[IPReputation]:
        # If ABUSEIPDB_API_KEY env var is empty: log warning, return None
        # AbuseIPDB v2: https://api.abuseipdb.com/api/v2/check
        # Params: ipAddress=<ip>, maxAgeInDays=90
        # Headers: Key=<abuseipdb_key>, Accept=application/json
        # On failure: return None, log warning

    def extract_public_ip(self, log_lines: list[str]) -> Optional[str]:
        # Regex: r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
        # Filter out private ranges: 10.x, 192.168.x, 172.16-31.x, 127.x
        # Return first non-private IP found across all lines
        # Return None if none found
```

### `triage/tools/historical_lookup.py`

```python
class HistoricalLookup:
    def __init__(self):
        # Load all-MiniLM-L6-v2 via sentence_transformers
        # ** This is NOT the same model as bert-base-uncased used in NeuralLog **
        # all-MiniLM-L6-v2 produces 384-dim vectors optimized for semantic similarity
        # bert-base-uncased produces 768-dim vectors for log message representation
        # Connect to Qdrant

    def find_similar(self, log_text: str, top_k: int = 3) -> list[dict]:
        # Embed log_text using all-MiniLM-L6-v2
        # Search Qdrant for top_k nearest neighbors by cosine similarity
        # Return [{"incident_id": str, "severity": str, "title": str}, ...]
        # If Qdrant collection is empty or unavailable: return []
```

### `triage/prompts/triage_prompt.py`

A function `build_prompt(raw_lines, anomaly_score, detection_source, mitre_result, ip_result, cve_results, similar_incidents) -> str` that returns a complete prompt string.

The prompt must:
- Identify the LLM as a SOC analyst assistant
- Provide the log evidence (raw lines)
- Provide anomaly score and detection source
- Provide MITRE match if any
- Provide IP reputation if any
- Provide CVE results if any
- Provide similar past incidents if any
- Instruct the LLM to output ONLY a valid JSON object matching the TriageReport schema
- Include severity classification rules inline:
  - Critical: active exploitation, privilege escalation success, reverse shell indicator
  - High: brute force with successful login, known malware pattern
  - Medium: brute force without successful login, port scanning
  - Low: single failed login, anomalous but low-confidence
  - Informational: anomaly score triggered but no clear threat
- End with: "Output ONLY the JSON object. No markdown. No explanation. No code fences."

### `triage/agent.py`

```python
class TriageAgent:
    def __init__(self):
        # Initialize all 4 tools
        # Initialize sentence-transformers model (all-MiniLM-L6-v2) for Qdrant embeddings
        # Initialize Qdrant client
        # Create collection if it does not exist:
        #   name=config.qdrant.collection, vector_size=384, distance=Cosine
        # Initialize LLM backend based on config:
        #   if groq: langchain_groq.ChatGroq with tools bound
        #   if ollama: langchain_ollama or raw HTTP client

    def run(self, sequence_message: dict) -> TriageReport:
        raw_lines = sequence_message["raw_lines"]
        anomaly_score = sequence_message.get("anomaly_score", 0.0)
        detection_source = sequence_message.get("detection_source", "unknown")

        if config["llm"]["provider"] == "groq":
            report = self._run_groq_react(raw_lines, anomaly_score, detection_source)
        else:
            report = self._run_ollama_deterministic(raw_lines, anomaly_score, detection_source)

        # Store in Qdrant
        self._store_report(report)

        # Publish to stream:triage_reports for future dashboard
        redis_client.xadd("stream:triage_reports", {"report": report.model_dump_json()})

        return report

    def _run_groq_react(self, raw_lines, anomaly_score, detection_source) -> TriageReport:
        # Use LangChain ReAct agent with tools bound to ChatGroq
        # The LLM decides which tools to call based on the log content
        # Tools are wrapped as LangChain Tool objects
        # Parse the final output into TriageReport
        # On failure: fall back to _run_ollama_deterministic or _fallback_report

    def _run_ollama_deterministic(self, raw_lines, anomaly_score, detection_source) -> TriageReport:
        # Step 1: Run all 4 tools deterministically
        mitre_result = self.mitre_mapper.map(raw_lines)
        public_ip = self.ip_checker.extract_public_ip(raw_lines)
        ip_result = self.ip_checker.check(public_ip) if public_ip else None
        keyword = self._extract_software_keyword(raw_lines)
        cve_results = self.cve_lookup.lookup(keyword) if keyword else []
        similar = self.historical_lookup.find_similar(" ".join(raw_lines))

        # Step 2: Build prompt with all tool results injected
        prompt = build_prompt(raw_lines, anomaly_score, detection_source,
                              mitre_result, ip_result, cve_results, similar)

        # Step 3: Call Ollama
        report_json = self._call_ollama(prompt)

        # Step 4: Parse into TriageReport
        try:
            report = TriageReport(**report_json)
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}\nRaw: {report_json}")
            report = self._fallback_report(raw_lines, anomaly_score, detection_source)

        return report

    def _call_ollama(self, prompt: str) -> dict:
        # POST to ollama_base_url/api/generate
        # Body: {"model": ollama_model, "prompt": prompt, "stream": false}
        # Extract response["response"]
        # Strip any markdown fences if present
        # Parse as JSON and return dict

    def _store_report(self, report: TriageReport):
        # Embed: title + " " + description + " " + " ".join(remediation_steps)
        # Use all-MiniLM-L6-v2 (NOT bert-base-uncased)
        # Upsert into Qdrant: id=UUID from incident_id, vector=embedding, payload=report.model_dump()

    def _fallback_report(self, raw_lines, anomaly_score, detection_source) -> TriageReport:
        # Return a minimal valid TriageReport indicating LLM failure
        # severity: "Low", description: "LLM triage failed -- manual review required"

    def _extract_software_keyword(self, raw_lines: list[str]) -> Optional[str]:
        # Regex search for known software names: sshd, apache, nginx, mysql, openssh
        # Return first match or None
```

### Stage 4 verification

After building stage 4, output:
1. All packages to add with `uv add`
2. Exact docker command to start Qdrant
3. How to verify Groq API key is working (a simple test call)
4. How to verify Ollama is running and the model is pulled (if using fallback)
5. How to run the full pipeline end-to-end (all 4 processes in separate terminals)
6. How to verify a triage report was stored in Qdrant (exact API call or Python snippet)
7. What a complete correct triage report JSON looks like
8. What to expect when AbuseIPDB/NVD keys are not set (should degrade gracefully, not crash)

**Stop here. Wait for the user to confirm stage 4 works.**

---

## FINAL DELIVERABLES AFTER ALL STAGES CONFIRMED

### `scripts/setup.sh`

Check Redis is reachable. Check Qdrant is reachable. Check Groq API key is set in
environment (and optionally check Ollama if fallback is needed). Run `setup_consumer_groups()`.
Create Qdrant collection if not exists. Print a clear READY or FAILED status for each check.

### `scripts/run_pipeline.sh`

```bash
#!/bin/bash
set -e
source .env 2>/dev/null || true
mkdir -p logs
python -m ingestion.producer --mode attack --rate 2 > logs/producer.log 2>&1 &
echo "[run] producer started (PID $!)"
python -m preprocessing.sequence_builder > logs/preprocessor.log 2>&1 &
echo "[run] sequence_builder started (PID $!)"
python -m queue.queue_a_worker > logs/queue_a.log 2>&1 &
echo "[run] queue_a_worker started (PID $!)"
python -m queue.queue_b_worker > logs/queue_b.log 2>&1 &
echo "[run] queue_b_worker started (PID $!)"
echo "[run] Pipeline running. Tail logs/ to monitor."
```

### `pyproject.toml`

Include all dependencies with version constraints. Key packages:
- `redis` -- Redis client for Streams
- `pyyaml` -- Config file parsing
- `python-dotenv` -- Environment variable loading
- `torch` -- PyTorch for NeuralLog
- `transformers` -- HuggingFace BERT model
- `sentence-transformers` -- all-MiniLM-L6-v2 for report embeddings
- `qdrant-client` -- Qdrant vector DB client
- `langchain` -- Agent framework
- `langchain-groq` -- Groq LLM integration
- `langchain-ollama` -- Ollama LLM integration (fallback)
- `pydantic` -- Data validation and schemas
- `requests` -- HTTP client for NVD/AbuseIPDB APIs
- `scikit-learn` -- Evaluation metrics (F1, precision, recall)
- `numpy` -- Array operations

### `README.md`

Include:
- Prerequisites (Python 3.11+, Redis, Docker for Qdrant, Groq API key)
- Setup steps (clone repo, `uv sync`, copy `.env.example` to `.env` and fill in keys, run `setup.sh`)
- How to download datasets (`bash scripts/download_datasets.sh`)
- How to train NeuralLog (`python -m detection.neurallog.train --dataset synthetic`)
- How to run the pipeline (`bash scripts/run_pipeline.sh`)
- How to verify it is working (what to check in Redis, what to check in Qdrant)
- How to switch between Groq and Ollama (change `llm.provider` in settings.yaml)
- How to train on real datasets when downloaded (use `--dataset hdfs` or `--dataset bgl`)
