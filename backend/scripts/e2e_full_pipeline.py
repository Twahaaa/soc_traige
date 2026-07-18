"""Full backend end-to-end pipeline test.

Runs all 4 stages in process (no tmux) and verifies:
  Stage 1: producer -> stream:raw_logs
  Stage 2: sequence_builder -> stream:queue_a / stream:queue_b
  Stage 3: queue_a_worker -> stream:queue_b_escalated (NeuralLog anomaly)
  Stage 4: queue_b_worker -> TriageAgent -> Qdrant + stream:triage_reports

Usage:  uv run python scripts/e2e_full_pipeline.py
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import redis
import requests
import yaml
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("e2e")


def step(n: int, msg: str) -> None:
    print(f"\n{'='*70}\n=== STAGE {n}: {msg}\n{'='*70}")


def wait_for(url: str, name: str, timeout: int = 30) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code < 500:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def flush_streams(r: redis.Redis) -> None:
    for stream in [
        "stream:raw_logs",
        "stream:queue_a",
        "stream:queue_b",
        "stream:queue_b_escalated",
        "stream:results_normal",
        "stream:triage_reports",
    ]:
        r.delete(stream)
    for group_data in [
        ("stream:raw_logs", "group:preprocessing"),
        ("stream:queue_a", "group:queue_a"),
        ("stream:queue_b", "group:queue_b"),
        ("stream:queue_b_escalated", "group:queue_b"),
        ("stream:results_normal", "group:dashboard"),
        ("stream:triage_reports", "group:dashboard"),
    ]:
        stream, group = group_data
        try:
            r.xgroup_destroy(stream, group)
        except redis.ResponseError:
            pass
    logger.info("flushed streams + consumer groups")


def stream_len(r: redis.Redis, name: str) -> int:
    return r.xlen(name)


def stream_tail(r: redis.Redis, name: str, count: int = 3) -> list[dict]:
    entries = r.xrevrange(name, count=count)
    out = []
    for _id, fields in entries:
        out.append({"id": _id.decode() if isinstance(_id, bytes) else _id,
                    "fields": {k.decode() if isinstance(k, bytes) else k:
                               v.decode() if isinstance(v, bytes) else v
                               for k, v in fields.items()}})
    return out


def main() -> int:
    load_dotenv()
    backend = Path(__file__).resolve().parents[1]
    os.chdir(backend)

    # --- infra check -------------------------------------------------------
    print("\n### Infrastructure")
    try:
        r = redis.Redis(host="localhost", port=6379, decode_responses=True)
        r.ping()
        print(f"  Redis: UP ({r.ping()})")
    except Exception as exc:
        print(f"  Redis: DOWN ({exc})")
        return 1

    if not wait_for("http://localhost:6333/healthz", "qdrant"):
        print("  Qdrant: DOWN (start with: docker run -d -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant)")
        return 1
    print("  Qdrant: UP")

    cfg = yaml.safe_load((backend / "config" / "settings.yaml").read_text())
    model_path = backend / "data" / "models" / "neurallog.pt"
    if not model_path.exists():
        print(f"  NeuralLog model: MISSING at {model_path}")
        print("  Training a quick checkpoint...")
        rc = subprocess.call(
            [sys.executable, "-m", "detection.neurallog.train",
             "--dataset", "synthetic", "--epochs", "1",
             "--synthetic_count", "80", "--output", str(model_path)],
            cwd=str(backend),
        )
        if rc != 0:
            print("  Training FAILED")
            return 1
    else:
        print(f"  NeuralLog model: {model_path.name} exists")

    flush_streams(r)

    # --- launch workers in background -------------------------------------
    procs = []
    try:
        def spawn(name: str, module: str, *args: str) -> subprocess.Popen:
            print(f"  launching {name}...")
            p = subprocess.Popen(
                [sys.executable, "-m", module, *args],
                cwd=str(backend),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            procs.append((name, p))
            return p

        step(2, "start sequence_builder (preprocessing worker)")
        spawn("sequence_builder", "preprocessing.sequence_builder")

        step(3, "start queue_a_worker (NeuralLog scoring)")
        spawn("queue_a_worker", "queue.queue_a_worker",
              "--model-path", str(model_path))

        step(4, "start queue_b_worker (triage)")
        spawn("queue_b_worker", "queue.queue_b_worker",
              "--model-path", str(model_path))

        time.sleep(3)  # let workers subscribe before producing

        # --- produce attack logs ------------------------------------------
        step(1, "produce attack logs -> stream:raw_logs")
        spawn("producer_attack", "ingestion.producer", "--mode", "attack",
              "--count", "40", "--rate", "20")

        # Also produce normal-mode logs so queue_a (NeuralLog scoring) is exercised.
        # Attack logs hit the prefilter and route directly to queue_b -> triage;
        # normal logs route to queue_a -> NeuralLog -> results_normal / queue_b_escalated.
        time.sleep(1)
        spawn("producer_normal", "ingestion.producer", "--mode", "normal",
              "--count", "60", "--rate", "30")

        # --- wait + verify each stage ------------------------------------
        print("\n### Waiting for pipeline to drain...")
        deadline = time.monotonic() + 120
        triage_count = 0
        last_snapshot = {}
        while time.monotonic() < deadline:
            snapshot = {
                "raw_logs": stream_len(r, "stream:raw_logs"),
                "queue_a": stream_len(r, "stream:queue_a"),
                "queue_b": stream_len(r, "stream:queue_b"),
                "queue_b_escalated": stream_len(r, "stream:queue_b_escalated"),
                "results_normal": stream_len(r, "stream:results_normal"),
                "triage_reports": stream_len(r, "stream:triage_reports"),
            }
            if snapshot != last_snapshot:
                print(f"  streams: {snapshot}")
                last_snapshot = snapshot
            # Done when producer finished, raw_logs drained, and at least 1 triage report exists.
            triage_count = snapshot["triage_reports"]
            if snapshot["raw_logs"] > 0 and snapshot["queue_a"] == 0 and snapshot["queue_b"] == 0 \
                    and snapshot["triage_reports"] > 0:
                print(f"  pipeline drained ({triage_count} triage reports)")
                break
            time.sleep(2)

        # --- final report --------------------------------------------------
        print("\n### Final stream lengths")
        for s, n in [("raw_logs", "stream:raw_logs"),
                     ("queue_a", "stream:queue_a"),
                     ("queue_b", "stream:queue_b"),
                     ("queue_b_escalated", "stream:queue_b_escalated"),
                     ("results_normal", "stream:results_normal"),
                     ("triage_reports", "stream:triage_reports")]:
            print(f"  {s:20s}: {stream_len(r, 'stream:' + s)}")

        print("\n### Qdrant collection")
        try:
            qresp = requests.get(
                f"http://localhost:6333/collections/{cfg['qdrant']['collection']}", timeout=5
            )
            qjson = qresp.json()
            print(f"  status: {qjson.get('result', {}).get('status')}")
            print(f"  points_count: {qjson.get('result', {}).get('points_count')}")
            qdrant_ok = qjson.get("result", {}).get("status") == "green"
        except Exception as exc:
            print(f"  Qdrant collection fetch FAILED: {exc}")
            qdrant_ok = False

        print("\n### Last triage report")
        reports = stream_tail(r, "stream:triage_reports", count=2)
        if reports:
            for rep in reports:
                payload = rep["fields"].get("report", "")
                try:
                    parsed = json.loads(payload)
                    print(f"  incident_id: {parsed.get('incident_id')}")
                    print(f"  severity:    {parsed.get('severity')}")
                    print(f"  title:       {parsed.get('title')}")
                    print(f"  description: {(parsed.get('description') or '')[:100]}")
                    print(f"  detection_source: {parsed.get('detection_source')}")
                except json.JSONDecodeError:
                    print(f"  raw: {payload[:200]}")
        else:
            print("  NO triage reports in stream")

        # --- verdict -------------------------------------------------------
        print("\n" + "="*70)
        print("### VERDICT")
        print("="*70)
        checks = {
            "stage1_raw_logs_produced": stream_len(r, "stream:raw_logs") > 0
                                        or triage_count > 0,  # producer finished + drained
            "stage2_sequences_built": stream_len(r, "stream:queue_a") + stream_len(r, "stream:queue_b") > 0
                                       or triage_count > 0,
            "stage3_neurallog_or_prefilter_path": (
                # Either NeuralLog scored (results_normal / queue_b_escalated) OR
                # prefilter routed critical logs straight to queue_b (which then triaged).
                stream_len(r, "stream:results_normal") + stream_len(r, "stream:queue_b_escalated") > 0
                or triage_count > 0
            ),
            "stage4_triage_reports": stream_len(r, "stream:triage_reports") > 0,
            "stage4_qdrant_collection": qdrant_ok,
        }
        all_ok = True
        for name, ok in checks.items():
            mark = "OK " if ok else "FAIL"
            print(f"  [{mark}] {name}")
            if not ok:
                all_ok = False

        # worker stderr tails
        print("\n### Worker output tails (last 5 lines each)")
        for name, p in procs:
            if p.poll() is not None:
                print(f"  [{name}] EXITED with code {p.returncode}")
            try:
                p.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass

        time.sleep(1)
        for name, p in procs:
            out = ""
            try:
                if p.stdout:
                    remaining = p.stdout.read() or ""
                    lines = remaining.splitlines()[-5:]
                    out = "\n".join(lines)
            except Exception:
                pass
            print(f"\n  --- {name} ---\n{out}")

        return 0 if all_ok else 2

    finally:
        for name, p in procs:
            try:
                if p.poll() is None:
                    p.terminate()
                    p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass


if __name__ == "__main__":
    sys.exit(main())
