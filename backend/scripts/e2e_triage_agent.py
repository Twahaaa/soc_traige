"""End-to-end smoke test for TriageAgent.run() with live LLM providers.

Run with:  uv run python scripts/e2e_triage_agent.py

Constructs a sample anomaly sequence message, runs the full agent pipeline
(tools -> prompt -> LLM chain -> JSON parse -> TriageReport -> storage),
and prints the resulting report. Storage backends (Qdrant/Redis) degrade
gracefully if unavailable.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

from triage.agent import TriageAgent  # noqa: E402


SAMPLE_SEQUENCE = {
    "raw_lines": [
        "2026-07-18T10:15:42 host-web-01 sshd[8341]: Failed password for invalid user admin from 203.0.113.5 port 51022 ssh2",
        "2026-07-18T10:15:45 host-web-01 sshd[8342]: Failed password for invalid user root from 203.0.113.5 port 51024 ssh2",
        "2026-07-18T10:15:48 host-web-01 sshd[8343]: Failed password for invalid user ubuntu from 203.0.113.5 port 51026 ssh2",
        "2026-07-18T10:15:51 host-web-01 sshd[8344]: Failed password for invalid user postgres from 203.0.113.5 port 51028 ssh2",
        "2026-07-18T10:15:54 host-web-01 sshd[8345]: Failed password for invalid user nginx from 203.0.113.5 port 51030 ssh2",
    ],
    "anomaly_score": 0.87,
    "detection_source": "neurallog",
    "source": "synthetic",
}


def main() -> int:
    print("\n=== Building TriageAgent (loads config + chain) ===")
    agent = TriageAgent()
    chain_names = [c.name for c in agent.llm_chain.clients]
    available = [c.name for c in agent.llm_chain.clients if c.is_available()]
    print(f"  llm_chain order:    {chain_names}")
    print(f"  llm_chain available: {available}")
    print(f"  qdrant_available:  {agent.qdrant_available}")

    print("\n=== Running agent on sample SSH brute-force sequence ===")
    report = agent.run(SAMPLE_SEQUENCE)

    print("\n=== Resulting TriageReport ===")
    payload = report.model_dump()
    # Print field-by-field with truncation for long fields
    for key, value in payload.items():
        if key == "evidence":
            print(f"  {key}: [{len(value)} lines]")
        elif isinstance(value, str) and len(value) > 120:
            print(f"  {key}: {value[:120]}...")
        elif isinstance(value, list) and len(str(value)) > 120:
            print(f"  {key}: {value[:3]}... ({len(value)} items)")
        else:
            print(f"  {key}: {value}")

    print("\n=== Report JSON (full) ===")
    print(json.dumps(payload, indent=2, default=str)[:2000])

    print("\n=== Done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
