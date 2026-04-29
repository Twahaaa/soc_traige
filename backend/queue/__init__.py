"""Queue package for Redis stream workers and helpers.

This package name shadows the stdlib `queue` module when running from backend/.
Expose standard queue classes so third-party imports keep working.
"""

from __future__ import annotations

import importlib.util
import sysconfig
from pathlib import Path
from types import ModuleType


def _load_stdlib_queue() -> ModuleType:
    stdlib_path = Path(sysconfig.get_path("stdlib") or "")
    queue_path = stdlib_path / "queue.py"
    spec = importlib.util.spec_from_file_location("_stdlib_queue", queue_path)
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load standard library queue module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_stdlib_queue = _load_stdlib_queue()

Empty = _stdlib_queue.Empty
Full = _stdlib_queue.Full
Queue = _stdlib_queue.Queue
LifoQueue = _stdlib_queue.LifoQueue
PriorityQueue = _stdlib_queue.PriorityQueue
SimpleQueue = _stdlib_queue.SimpleQueue

__all__ = [
    "Empty",
    "Full",
    "Queue",
    "LifoQueue",
    "PriorityQueue",
    "SimpleQueue",
]
