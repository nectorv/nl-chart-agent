from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

_LOG_FILE = Path(__file__).parent.parent.parent / "logs" / "pipeline.jsonl"
_LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_pipeline_step(
    run_id: str,
    query: str,
    step: str,
    duration_ms: int,
    outcome: str,
    metadata: dict | None = None,
) -> None:
    entry = {
        "run_id": run_id,
        "query": query,
        "step": step,
        "duration_ms": duration_ms,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
    }
    with _LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def log_eval_iteration(
    run_id: str,
    query: str,
    iteration: int,
    data_fit_score: int,
    intent_match_score: int,
    issues: list[str],
    outcome: str,
) -> None:
    entry = {
        "run_id": run_id,
        "query": query,
        "iteration": iteration,
        "data_fit_score": data_fit_score,
        "intent_match_score": intent_match_score,
        "issues": issues,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def new_run_id() -> str:
    return str(uuid.uuid4())
