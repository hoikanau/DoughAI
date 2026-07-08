"""Append-only recommendation log.

Every verdict the agent produces gets appended here, keyed by ticker and
timestamp. Never overwrite past entries — this is what the eventual
backtest/eval loop (docs/ARCHITECTURE.md section 6) scores against later.
"""

from __future__ import annotations

import json
import os

DEFAULT_LOG_PATH = os.environ.get("DOUGHAI_LOG_PATH", "data/recommendations.jsonl")


def log_verdict(verdict: dict, path: str = DEFAULT_LOG_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(verdict, default=str) + "\n")
