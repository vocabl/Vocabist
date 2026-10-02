"""
Vocabist database factory.

Reads DB_BACKEND from the environment (via .env or shell):
  - "mongo"    -> MongoRepository  (Motor / AsyncIOMotorClient)  [DEFAULT]
  - "supabase" -> SupabaseRepository (supabase-py AsyncClient)
  - "dual"     -> DualWriteRepository (Mongo authoritative + Supabase mirror)
                  also requires DUAL_WRITE_ENABLED=true in environment
  - not set     -> defaults to "mongo"
  - any other   -> ValueError  (never silently defaults to Supabase)
"""
import os
from dotenv import load_dotenv

load_dotenv()

_repo = None


def get_db():
    """Return the singleton DatabaseRepository for the configured backend."""
    global _repo
    if _repo is None:
        raw = os.environ.get("DB_BACKEND") or ""
        backend = raw.lower().strip()
        if not backend or backend == "mongo":
            from db.mongo_repo import MongoRepository
            _repo = MongoRepository()
        elif backend == "supabase":
            from db.supabase_repo import SupabaseRepository
            _repo = SupabaseRepository()
        elif backend == "dual":
            dual_enabled = os.environ.get("DUAL_WRITE_ENABLED", "false").lower() == "true"
            if not dual_enabled:
                # Safety: if DUAL_WRITE_ENABLED is not explicitly true, fall back to Mongo
                import logging
                logging.getLogger("vocabist.db").warning(
                    "DB_BACKEND=dual but DUAL_WRITE_ENABLED is not 'true' — "
                    "defaulting to MongoRepository for safety."
                )
                from db.mongo_repo import MongoRepository
                _repo = MongoRepository()
            else:
                from db.dual_write_repo import DualWriteRepository
                _repo = DualWriteRepository()
        else:
            raise ValueError(
                f"Invalid DB_BACKEND='{raw}'. "
                "Accepted values: 'mongo' (default), 'supabase', or 'dual'. "
                "An explicitly invalid value is never silently overridden."
            )
    return _repo


def reset_db_for_testing():
    """Reset singleton — intended for test isolation only."""
    global _repo
    _repo = None
