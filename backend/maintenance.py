"""
Vocabist — Backend Maintenance CLI
====================================
Runs heavyweight database maintenance / migration operations that must NOT
execute automatically on every application startup.

Usage (run from /app/backend):
    python maintenance.py --help
    python maintenance.py canonical          # migrate_canonical()
    python maintenance.py lifecycle          # migrate_content_lifecycle()
    python maintenance.py resolve_refs       # resolve_all_relationship_refs()
    python maintenance.py all                # run all three in sequence

IMPORTANT:
- These operations mutate database records.  Run them deliberately.
- Never execute this file automatically from a process manager (supervisord,
  systemd, etc.).  It is an operator tool.
- The DB_BACKEND environment variable controls which database is targeted.
  Confirm DB_BACKEND before running:
      echo $DB_BACKEND        # blank = mongo (default)
      DB_BACKEND=supabase python maintenance.py canonical
- Do NOT run during peak traffic.  These operations load all vocabulary
  records and update them iteratively.
- Estimated runtime (231 words, local Mongo): < 2 seconds
  Estimated runtime (231 words, Supabase over HTTP): 10 – 20 seconds

Safety:
- All three operations are idempotent:  a word that has already been
  migrated will be skipped on re-runs.
- No vocabulary records are deleted.
- No user data is affected.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

# ---------------------------------------------------------------------------
# Make sure the backend package root is on sys.path when running as a script.
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

# ---------------------------------------------------------------------------
# Lazy imports — only after env vars are loaded.
# ---------------------------------------------------------------------------

def _imports():
    from db import get_db
    from content_ingest import migrate_content_lifecycle, migrate_canonical
    from graph_service import resolve_all_relationship_refs
    return get_db, migrate_content_lifecycle, resolve_all_relationship_refs, migrate_canonical


COMMANDS = {
    "canonical":      "migrate_canonical()    — upgrade all words to canonical schema v1",
    "lifecycle":      "migrate_content_lifecycle() — standardise provenance + lifecycle_version",
    "resolve_refs":   "resolve_all_relationship_refs() — resolve relation headword→id pointers",
    "all":            "run canonical → lifecycle → resolve_refs in sequence",
    "reconcile":      "reconcile_and_sync — compare Mongo vs Supabase; sync missing records",
    "inspect_outbox": "show unresolved dual-write outbox entries",
    "retry_outbox":   "retry failed Supabase mirror writes from the outbox",
}

HELP = f"""
Vocabist Maintenance CLI
========================
Available commands:
""" + "\n".join(f"  {k:<16} {v}" for k, v in COMMANDS.items()) + """

Environment:
  DB_BACKEND    mongo (default) | supabase | dual
  DUAL_WRITE_ENABLED  true | false (default)

Examples:
  DB_BACKEND=supabase python maintenance.py all
  python maintenance.py reconcile
  python maintenance.py inspect_outbox
  python maintenance.py retry_outbox
"""


async def run(cmd: str) -> None:
    get_db, migrate_content_lifecycle, resolve_all_relationship_refs, migrate_canonical = _imports()
    repo = get_db()
    backend = os.environ.get("DB_BACKEND", "mongo")
    print(f"[maintenance] DB_BACKEND={backend}")

    if cmd in ("canonical", "all"):
        t = time.perf_counter()
        print("[maintenance] Running migrate_canonical() …")
        await migrate_canonical(repo)
        print(f"[maintenance] migrate_canonical() done in {time.perf_counter()-t:.1f}s")

    if cmd in ("lifecycle", "all"):
        t = time.perf_counter()
        print("[maintenance] Running migrate_content_lifecycle() …")
        n = await migrate_content_lifecycle(repo)
        print(f"[maintenance] migrate_content_lifecycle() → {n} updated in {time.perf_counter()-t:.1f}s")

    if cmd in ("resolve_refs", "all"):
        t = time.perf_counter()
        print("[maintenance] Running resolve_all_relationship_refs() …")
        stats = await resolve_all_relationship_refs(repo)
        print(f"[maintenance] resolve_all_relationship_refs() → {stats} in {time.perf_counter()-t:.1f}s")

    if cmd == "reconcile":
        t = time.perf_counter()
        print("[maintenance] Running reconcile_and_sync (Mongo → Supabase) …")
        import sys as _sys
        _sys.path.insert(0, _BACKEND_DIR)
        from migrations.reconcile_and_sync import run as reconcile_run, MIGRATION_ORDER
        await reconcile_run(MIGRATION_ORDER, dry_run=False, report_only=False)
        print(f"[maintenance] reconcile_and_sync done in {time.perf_counter()-t:.1f}s")

    if cmd == "inspect_outbox":
        print("[maintenance] Inspecting dual_write_outbox …")
        from db.dual_write_repo import DualWriteRepository
        dw = DualWriteRepository()
        docs = await dw.get_outbox_unresolved()
        if not docs:
            print("[maintenance] No unresolved outbox entries.")
        else:
            print(f"[maintenance] {len(docs)} unresolved entries:")
            for d in docs:
                print(f"  [{d['collection']}] {d['operation']} pk={d['pk_value']}"
                      f" retries={d['retry_count']} error={d['error'][:80]}")

    if cmd == "retry_outbox":
        print("[maintenance] Retrying failed Supabase mirror writes …")
        from db.dual_write_repo import DualWriteRepository
        dw = DualWriteRepository()
        result = await dw.retry_outbox()
        print(f"[maintenance] Outbox retry: resolved={result['resolved']}"
              f" failed={result['failed']} total={result['total']}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args or sys.argv[1] in ("-h", "--help"):
        print(HELP)
        sys.exit(0)

    cmd = args[0]
    if cmd not in COMMANDS:
        print(f"[maintenance] Unknown command: {cmd!r}")
        print(f"[maintenance] Valid commands: {', '.join(COMMANDS)}")
        sys.exit(1)

    print(f"[maintenance] Starting: {cmd}")
    asyncio.run(run(cmd))
    print("[maintenance] Done.")


if __name__ == "__main__":
    main()
