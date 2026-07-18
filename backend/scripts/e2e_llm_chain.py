"""End-to-end smoke test for the LLM wrapper against live providers.

Run with:  uv run python scripts/e2e_llm_chain.py

Prints safe (key-redacted) status output. Does NOT print full LLM responses
to avoid leaking potentially sensitive content; only shows length + first 80
chars of any returned content.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Ensure backend/ is on sys.path when run via `uv run python scripts/...`
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from triage.llm.base import LLMClient, ProviderError  # noqa: E402
from triage.llm.chain import LLMChain  # noqa: E402
from triage.llm.factory import build_chain  # noqa: E402
from triage.llm.providers import (  # noqa: E402
    build_groq,
    build_ollama,
    build_opencode_go,
    build_openrouter,
)

PROMPT = (
    "You are a SOC analyst assistant. Respond with ONLY a JSON object with keys "
    "'severity' (one of Critical/High/Medium/Low/Informational) and 'title' (short string). "
    "Evidence: 3 failed SSH logins from 203.0.113.5 in 60 seconds. "
    'Anomaly score: 0.87. Output JSON only, e.g. {"severity":"Medium","title":"SSH brute force"}.'
)


def _redact(s: str, max_len: int = 80) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= max_len else s[:max_len] + "..."


def _env_status() -> None:
    print("\n=== Environment keys ===")
    for name in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENCODE_GO_API_KEY"):
        v = os.getenv(name, "").strip()
        print(f"  {name}: {'SET (' + str(len(v)) + ' chars)' if v else 'NOT SET'}")


def _provider_status(cfg: dict) -> None:
    print("\n=== Provider availability ===")
    timeout = float(cfg.get("retry", {}).get("timeout_seconds", 30))
    providers_cfg = cfg.get("providers", {})
    builders = {
        "groq": build_groq,
        "openrouter": build_openrouter,
        "opencode_go": build_opencode_go,
        "ollama": build_ollama,
    }
    for name, builder in builders.items():
        client = builder(providers_cfg.get(name) or {}, timeout)
        status = "available" if client.is_available() else f"UNAVAILABLE ({client.describe_unavailable()})"
        print(f"  {name}: {status}")


def _test_individual_providers(cfg: dict) -> dict[str, str | None]:
    print("\n=== Per-provider live invoke ===")
    timeout = float(cfg.get("retry", {}).get("timeout_seconds", 30))
    providers_cfg = cfg.get("providers", {})
    results: dict[str, str | None] = {}

    tests = [
        ("groq", build_groq(providers_cfg.get("groq") or {}, timeout)),
        ("openrouter", build_openrouter(providers_cfg.get("openrouter") or {}, timeout)),
        ("opencode_go", build_opencode_go(providers_cfg.get("opencode_go") or {}, timeout)),
        ("ollama", build_ollama(providers_cfg.get("ollama") or {}, timeout)),
    ]
    for name, client in tests:
        if not client.is_available():
            print(f"  [{name}] skipped (unavailable)")
            results[name] = None
            continue
        t0 = time.monotonic()
        try:
            content = client.invoke(PROMPT)
            elapsed = time.monotonic() - t0
            print(f"  [{name}] OK in {elapsed:.2f}s -> len={len(content)} preview={_redact(content)!r}")
            results[name] = content
        except ProviderError as exc:
            elapsed = time.monotonic() - t0
            print(f"  [{name}] FAILED in {elapsed:.2f}s -> {exc}")
            results[name] = None
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            print(f"  [{name}] UNEXPECTED ERROR in {elapsed:.2f}s -> {type(exc).__name__}: {exc}")
            results[name] = None
    return results


def _test_chain(cfg: dict) -> None:
    print("\n=== Chain end-to-end (build_chain + invoke) ===")
    chain = build_chain(cfg)
    print(f"  chain order: {[c.name for c in chain.clients]}")
    print(f"  available:   {[c.name for c in chain.clients if c.is_available()]}")
    t0 = time.monotonic()
    content = chain.invoke(PROMPT)
    elapsed = time.monotonic() - t0
    if content is None:
        print(f"  RESULT: None (all providers failed) in {elapsed:.2f}s")
    else:
        print(f"  RESULT: OK in {elapsed:.2f}s -> len={len(content)} preview={_redact(content)!r}")


def _test_fallback_to_deterministic(cfg: dict) -> None:
    """Force all providers unavailable and confirm chain returns None."""
    print("\n=== Fallback-to-None path (all providers forced unavailable) ===")
    chain = LLMChain(
        clients=[
            LLMClient("groq", None, available=False, unavailable_reason="forced"),
            LLMClient("openrouter", None, available=False, unavailable_reason="forced"),
            LLMClient("opencode_go", None, available=False, unavailable_reason="forced"),
            LLMClient("ollama", None, available=False, unavailable_reason="forced"),
        ],
        retries=0,
    )
    result = chain.invoke(PROMPT)
    print(f"  RESULT: {result!r}  (expected None -> triggers deterministic fallback in agent)")


def main() -> int:
    load_dotenv()
    cfg_path = BACKEND_ROOT / "config" / "settings.yaml"
    with cfg_path.open("r", encoding="utf-8") as fh:
        full_cfg = yaml.safe_load(fh)
    cfg = full_cfg["llm"]

    _env_status()
    _provider_status(cfg)
    _test_individual_providers(cfg)
    _test_chain(cfg)
    _test_fallback_to_deterministic(cfg)
    print("\n=== Done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
