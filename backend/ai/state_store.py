"""File-based persistence for AI platform runtime state.

We intentionally avoid Redis/Celery/new DB tables (per spec) and keep the
simplest reliable store compatible with the single-process FastAPI runtime:

    backend/ai/state/
        config.json        — model enable/disable + status + routing overrides
        usage.jsonl         — one JSON line per AI request (usage tracking)
        jobs/<job_id>.json  — one file per generation job

All reads/writes are guarded by an asyncio lock. This is single-pod only, which
matches the current deployment; the abstraction can later move to Supabase
tables without touching callers.
"""
from __future__ import annotations

import os
import json
import asyncio
from typing import Any, Dict, List, Optional

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
_JOBS_DIR = os.path.join(_DIR, "jobs")
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_USAGE_PATH = os.path.join(_DIR, "usage.jsonl")

os.makedirs(_JOBS_DIR, exist_ok=True)

_lock = asyncio.Lock()


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, default=str)
    os.replace(tmp, path)


# ----------------------------- config ------------------------------------- #
async def load_config() -> Dict[str, Any]:
    async with _lock:
        return _read_json(_CONFIG_PATH, {"models": {}, "routing": {}})


async def save_config(cfg: Dict[str, Any]) -> None:
    async with _lock:
        _write_json(_CONFIG_PATH, cfg)


async def update_model_state(model_key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    async with _lock:
        cfg = _read_json(_CONFIG_PATH, {"models": {}, "routing": {}})
        models = cfg.setdefault("models", {})
        cur = models.setdefault(model_key, {})
        cur.update(patch)
        _write_json(_CONFIG_PATH, cfg)
        return cur


async def set_routing(task: str, chain: List[str], enabled: bool = True) -> None:
    async with _lock:
        cfg = _read_json(_CONFIG_PATH, {"models": {}, "routing": {}})
        cfg.setdefault("routing", {})[task] = {"chain": chain, "enabled": enabled}
        _write_json(_CONFIG_PATH, cfg)


# ----------------------------- usage -------------------------------------- #
async def append_usage(record: Dict[str, Any]) -> None:
    async with _lock:
        try:
            with open(_USAGE_PATH, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception:
            pass


async def read_usage(limit: int = 5000) -> List[Dict[str, Any]]:
    async with _lock:
        if not os.path.exists(_USAGE_PATH):
            return []
        try:
            with open(_USAGE_PATH, "r") as f:
                lines = f.readlines()[-limit:]
        except Exception:
            return []
    out: List[Dict[str, Any]] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


# ----------------------------- jobs --------------------------------------- #
def _job_path(job_id: str) -> str:
    return os.path.join(_JOBS_DIR, f"{job_id}.json")


async def save_job(job: Dict[str, Any]) -> None:
    async with _lock:
        _write_json(_job_path(job["id"]), job)


async def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    async with _lock:
        return _read_json(_job_path(job_id), None)


async def update_job(job_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    async with _lock:
        job = _read_json(_job_path(job_id), None)
        if job is None:
            return None
        job.update(patch)
        _write_json(_job_path(job_id), job)
        return job


async def list_jobs(limit: int = 100) -> List[Dict[str, Any]]:
    async with _lock:
        files = [f for f in os.listdir(_JOBS_DIR) if f.endswith(".json")]
        jobs = [_read_json(os.path.join(_JOBS_DIR, f), None) for f in files]
    jobs = [j for j in jobs if j]
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return jobs[:limit]
