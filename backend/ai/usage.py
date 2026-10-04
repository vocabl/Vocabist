"""Centralized AI usage tracking + aggregation.

Never records API keys, passwords, session tokens, or raw sensitive content.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from . import state_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def record(
    *,
    task: str,
    provider: str,
    model: str,
    success: bool,
    latency_ms: int,
    fallback: bool = False,
    attempt: int = 0,
    error_code: Optional[str] = None,
    usage: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    admin_id: Optional[str] = None,
    job_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    usage = usage or {}
    await state_store.append_usage({
        "request_id": request_id or uuid.uuid4().hex,
        "ts": _now().isoformat(),
        "task": task,
        "provider": provider,
        "model": model,
        "success": bool(success),
        "fallback": bool(fallback),
        "attempt": attempt,
        "latency_ms": int(latency_ms),
        "error_code": error_code,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "user_id": user_id,
        "admin_id": admin_id,
        "job_id": job_id,
    })


def _parse_ts(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def aggregate() -> Dict[str, Any]:
    events = await state_store.read_usage(limit=8000)
    now = _now()
    today = now.date()
    week_ago = now - timedelta(days=7)

    total = len(events)
    today_events = 0
    week_events = 0
    success = 0
    failure = 0
    fallback = 0
    by_model: Dict[str, int] = {}
    by_task: Dict[str, int] = {}
    by_provider: Dict[str, int] = {}
    latency_sum = 0
    latency_n = 0
    tokens_total = 0
    tokens_known = False

    for e in events:
        ts = _parse_ts(e.get("ts"))
        if ts:
            if ts.date() == today:
                today_events += 1
            if ts >= week_ago:
                week_events += 1
        if e.get("success"):
            success += 1
        else:
            failure += 1
        if e.get("fallback"):
            fallback += 1
        by_model[e.get("model", "?")] = by_model.get(e.get("model", "?"), 0) + 1
        by_task[e.get("task", "?")] = by_task.get(e.get("task", "?"), 0) + 1
        by_provider[e.get("provider", "?")] = by_provider.get(e.get("provider", "?"), 0) + 1
        lm = e.get("latency_ms")
        if isinstance(lm, (int, float)):
            latency_sum += lm
            latency_n += 1
        tt = e.get("total_tokens")
        if isinstance(tt, (int, float)):
            tokens_total += tt
            tokens_known = True

    def rate(n: int) -> float:
        return round((n / total) * 100, 1) if total else 0.0

    return {
        "requests_total": total,
        "requests_today": today_events,
        "requests_week": week_events,
        "success": success,
        "failure": failure,
        "fallback_events": fallback,
        "success_rate": rate(success),
        "failure_rate": rate(failure),
        "fallback_rate": rate(fallback),
        "avg_latency_ms": round(latency_sum / latency_n) if latency_n else None,
        "by_model": by_model,
        "by_task": by_task,
        "by_provider": by_provider,
        "total_tokens": tokens_total if tokens_known else None,
        "token_info": "Available" if tokens_known else "Unavailable",
        "estimated_cost": "Unavailable",
    }
