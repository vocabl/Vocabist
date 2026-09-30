"""Developer content-quality report (Phase B).

Read-only validation pass over the existing vocabulary bank. Never modifies
records. Run from the backend directory:

    python content_report.py

Prints duplicate canonical keys, invalid records, and an issue histogram so
developers can gauge content health before scaling the bank.
"""
import asyncio
import json
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from content_ingest import quality_report

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT_DIR, ".env"))


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "vocably")]
    report = await quality_report(db)
    # Compact, human-readable summary.
    print(json.dumps({
        "total_words": report["total_words"],
        "invalid_count": report["invalid_count"],
        "duplicate_canonical_keys": report["duplicate_canonical_keys"],
        "missing_provenance": report["missing_provenance"],
        "invalid_status": report["invalid_status"],
        "issues_by_code": report["issues_by_code"],
    }, indent=2, default=str))
    if report["invalid_samples"]:
        print("\nInvalid samples (first 50):")
        for s in report["invalid_samples"]:
            print(f"  - {s['id']}: {[e['code'] for e in s['errors']]}")


if __name__ == "__main__":
    asyncio.run(main())
