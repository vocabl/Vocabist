"""Clean up test artifacts from MongoDB before final cutover."""
import asyncio
import os
import re
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient


async def cleanup():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "vocably")]

    pattern = re.compile(r"^(dw_|test_|mat_|matrix_)")

    # Count test users
    test_user_ids = []
    async for u in db.users.find({"user_id": pattern}, {"_id": 0, "user_id": 1}):
        test_user_ids.append(u["user_id"])
    print(f"Found {len(test_user_ids)} test users to clean up")

    if test_user_ids:
        r1 = await db.users.delete_many({"user_id": {"$in": test_user_ids}})
        r2 = await db.profiles.delete_many({"user_id": {"$in": test_user_ids}})
        r3 = await db.user_sessions.delete_many({"user_id": {"$in": test_user_ids}})
        r4 = await db.saved_words.delete_many({"user_id": {"$in": test_user_ids}})
        r5 = await db.user_word_progress.delete_many({"user_id": {"$in": test_user_ids}})
        print(f"  users={r1.deleted_count} profiles={r2.deleted_count} sessions={r3.deleted_count}")
        print(f"  saved_words={r4.deleted_count} progress={r5.deleted_count}")

    # Clean up all test sessions (user_id matching test_ / dw_ / mat_)
    r6 = await db.user_sessions.delete_many({"user_id": pattern})
    print(f"  extra sessions removed: {r6.deleted_count}")

    # Clear unresolved outbox entries (from testing)
    r7 = await db.dual_write_outbox.delete_many({"resolved": False})
    print(f"  cleared unresolved outbox entries: {r7.deleted_count}")

    # Also clean up orphaned tts cache entries from matrix tests  
    r8 = await db.tts_cache.delete_many({"key": {"$regex": "^matrix_tts_"}})
    print(f"  cleared test tts entries: {r8.deleted_count}")

    print("Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(cleanup())
