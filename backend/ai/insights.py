"""Model Insights — enhanced AI usage analytics with per-model metrics.

Extends the existing usage tracking with latency percentiles, quality signals,
model comparison, and task breakdown. All metrics are based on actual recorded
data — nothing is fabricated.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from . import state_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def model_insights(
    *,
    model_filter: Optional[str] = None,
    task_filter: Optional[str] = None,
    provider_filter: Optional[str] = None,
    days: int = 30,
) -> Dict[str, Any]:
    """Comprehensive model performance insights from actual usage data."""
    events = await state_store.read_usage(limit=10000)
    now = _now()
    cutoff = now - timedelta(days=days)

    # Filter events
    filtered = []
    for e in events:
        ts = _parse_ts(e.get("ts"))
        if ts and ts < cutoff:
            continue
        if model_filter and e.get("model") != model_filter:
            continue
        if task_filter and e.get("task") != task_filter:
            continue
        if provider_filter and e.get("provider") != provider_filter:
            continue
        filtered.append(e)

    # Per-model metrics
    by_model: Dict[str, Dict[str, Any]] = {}
    for e in filtered:
        model = e.get("model", "unknown")
        m = by_model.setdefault(model, {
            "model": model,
            "provider": e.get("provider", "unknown"),
            "requests": 0,
            "successful": 0,
            "failed": 0,
            "fallback_count": 0,
            "latencies": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "tokens_available": False,
            "tasks": {},
            "first_seen": None,
            "last_seen": None,
        })
        m["requests"] += 1
        if e.get("success"):
            m["successful"] += 1
        else:
            m["failed"] += 1
        if e.get("fallback"):
            m["fallback_count"] += 1

        lat = e.get("latency_ms")
        if isinstance(lat, (int, float)) and lat > 0:
            m["latencies"].append(lat)

        pt = e.get("prompt_tokens")
        ct = e.get("completion_tokens")
        tt = e.get("total_tokens")
        if isinstance(pt, (int, float)):
            m["prompt_tokens"] += int(pt)
            m["tokens_available"] = True
        if isinstance(ct, (int, float)):
            m["completion_tokens"] += int(ct)
            m["tokens_available"] = True
        if isinstance(tt, (int, float)):
            m["total_tokens"] += int(tt)
            m["tokens_available"] = True

        task = e.get("task", "unknown")
        m["tasks"][task] = m["tasks"].get(task, 0) + 1

        ts = _parse_ts(e.get("ts"))
        if ts:
            if m["first_seen"] is None or ts < m["first_seen"]:
                m["first_seen"] = ts
            if m["last_seen"] is None or ts > m["last_seen"]:
                m["last_seen"] = ts

    # Compute derived metrics per model
    models = []
    for model_key, m in by_model.items():
        lats = m["latencies"]
        model_data = {
            "model": m["model"],
            "provider": m["provider"],
            "requests": m["requests"],
            "successful": m["successful"],
            "failed": m["failed"],
            "fallback_count": m["fallback_count"],
            "success_rate": round(m["successful"] / m["requests"] * 100, 1) if m["requests"] else 0,
            "failure_rate": round(m["failed"] / m["requests"] * 100, 1) if m["requests"] else 0,
            "fallback_rate": round(m["fallback_count"] / m["requests"] * 100, 1) if m["requests"] else 0,
            "avg_latency_ms": round(statistics.mean(lats)) if lats else None,
            "p50_latency_ms": round(statistics.median(lats)) if lats else None,
            "p95_latency_ms": round(_percentile(lats, 95)) if len(lats) >= 5 else None,
            "min_latency_ms": round(min(lats)) if lats else None,
            "max_latency_ms": round(max(lats)) if lats else None,
            "sample_count": len(lats),
            "tasks": m["tasks"],
            "tokens": {
                "prompt": m["prompt_tokens"],
                "completion": m["completion_tokens"],
                "total": m["total_tokens"],
                "available": m["tokens_available"],
            },
            "cost": "Unavailable",  # Never fabricate cost
            "first_seen": m["first_seen"].isoformat() if m["first_seen"] else None,
            "last_seen": m["last_seen"].isoformat() if m["last_seen"] else None,
        }
        models.append(model_data)

    # Sort by request count descending
    models.sort(key=lambda x: -x["requests"])

    # Task breakdown
    task_breakdown: Dict[str, Dict[str, Any]] = {}
    for e in filtered:
        task = e.get("task", "unknown")
        t = task_breakdown.setdefault(task, {
            "task": task,
            "requests": 0,
            "successful": 0,
            "failed": 0,
            "fallback_count": 0,
            "latencies": [],
            "models_used": set(),
        })
        t["requests"] += 1
        if e.get("success"):
            t["successful"] += 1
        else:
            t["failed"] += 1
        if e.get("fallback"):
            t["fallback_count"] += 1
        lat = e.get("latency_ms")
        if isinstance(lat, (int, float)) and lat > 0:
            t["latencies"].append(lat)
        t["models_used"].add(e.get("model", "unknown"))

    tasks = []
    for task_name, t in task_breakdown.items():
        lats = t["latencies"]
        tasks.append({
            "task": t["task"],
            "requests": t["requests"],
            "successful": t["successful"],
            "failed": t["failed"],
            "fallback_count": t["fallback_count"],
            "success_rate": round(t["successful"] / t["requests"] * 100, 1) if t["requests"] else 0,
            "avg_latency_ms": round(statistics.mean(lats)) if lats else None,
            "models_used": list(t["models_used"]),
        })
    tasks.sort(key=lambda x: -x["requests"])

    # Summary
    total_requests = sum(m["requests"] for m in models)
    total_success = sum(m["successful"] for m in models)
    total_fallback = sum(m["fallback_count"] for m in models)
    all_lats = [l for m in by_model.values() for l in m["latencies"]]

    return {
        "period_days": days,
        "total_requests": total_requests,
        "total_successful": total_success,
        "total_failed": total_requests - total_success,
        "total_fallback": total_fallback,
        "overall_success_rate": round(total_success / total_requests * 100, 1) if total_requests else 0,
        "overall_avg_latency_ms": round(statistics.mean(all_lats)) if all_lats else None,
        "models": models,
        "tasks": tasks,
        "filters_applied": {
            "model": model_filter,
            "task": task_filter,
            "provider": provider_filter,
            "days": days,
        },
    }


def _percentile(data: List[float], p: float) -> float:
    """Calculate percentile from a sorted list."""
    if not data:
        return 0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])
