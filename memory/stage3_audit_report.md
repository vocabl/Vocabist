# VOCABIST — Stage 3 Supabase Application Switchover: Final Audit Report

**Generated:** 2026-06-27  
**Status:** AUDIT ONLY — No implementation code written  
**MongoDB:** ACTIVE (unchanged)  
**Supabase:** Schema verified, data migrated (377 records). Application not yet connected.

---

## Notation Key

| Symbol | Meaning |
|---|---|
| ✅ CONFIRMED FACT | Verified directly from code/schema inspection |
| 🔷 PROPOSED ARCHITECTURE | Design decision, not yet implemented |
| ⚠️ ASSUMPTION | Inferred but not directly verifiable without running code |
| ❌ UNRESOLVED BLOCKER | Requires decision before implementation |
| 🔥 HIGH RISK | Could cause data loss, race condition, or silent failure |

---

## Part 1 — Complete MongoDB Operation Inventory

### Collections Active in MongoDB (✅ CONFIRMED from live count)

| Collection | Records | Type |
|---|---|---|
| `words` | 231 | Canonical; updated in-place |
| `users` | 18 | Auth; updated in-place |
| `user_sessions` | 19 | Append + delete |
| `profiles` | 13 | Updated in-place |
| `user_word_progress` | 10 | Upserted per answer |
| `saved_words` | 2 | Upserted + deleted |
| `analytics_events` | 71 | Append-only |
| `study_sessions` | 3 | Append-only |
| `ai_coach_content` | 5 | Append-only (immutable after write) |
| `ai_coach_usage` | 5 | Append-only |
| `tts_cache` | 1 | Keyed cache |
| `topics` | 6 | Static reference |
| `exams` | 6 | Static reference |
| `articles` | 4 | Static reference |
| `subscriptions` | 2 | Upserted in-place |

---

## Part 2 — Full Operation Map: Every `db.*` Call by Endpoint

### AUTH ROUTES

#### `get_current_user` ← dependency called by ALL 30+ authenticated routes

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| A1 | `find_one({"session_token": token}, {"_id": 0})` | `user_sessions` | Point read by token |
| A2 | `find_one({"user_id": session["user_id"]}, {"_id": 0})` | `users` | Point read by user_id |

#### `create_session` ← called by register, login, google_session

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| A3 | `insert_one({session_token, user_id, created_at, expires_at})` | `user_sessions` | Insert |

#### `POST /api/auth/register`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| A4 | `find_one({"email": email})` | `users` | Point read |
| A5 | `insert_one({user_id, email, name, password_hash, ...})` | `users` | Insert |
| A6 | `find_one({"user_id": user_id}, {"_id": 0})` | `users` | Point read (read-back) |
| A3 | *(create_session)* | `user_sessions` | Insert |

#### `POST /api/auth/login`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| A7 | `find_one({"email": email})` | `users` | Point read |
| A3 | *(create_session)* | `user_sessions` | Insert |

#### `POST /api/auth/session` (Google OAuth)

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| A8 | `find_one({"email": email})` | `users` | Point read |
| A9 | `insert_one({...})` | `users` | Conditional insert (if new user) |
| A10 | `find_one({"user_id": user_id})` | `users` | Point read (read-back) |
| A3 | *(create_session)* | `user_sessions` | Insert |

#### `POST /api/auth/logout`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| A11 | `delete_one({"session_token": token})` | `user_sessions` | Delete by token |

---

### PROFILE / ONBOARDING ROUTES

#### `get_or_create_profile` ← called by 8+ routes

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| P1 | `find_one({"user_id": user_id}, {"_id": 0})` | `profiles` | Point read |
| P2 | `insert_one({user_id, reason: None, level: None, ...})` | `profiles` | Conditional insert |

#### `POST /api/onboarding`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| P1/P2 | *(get_or_create_profile)* | `profiles` | Read/insert |
| P3 | `update_one({"user_id"}, {"$set": {reason, level, daily_minutes, ...}})` | `profiles` | Partial update |
| P4 | `update_one({"user_id"}, {"$set": {"onboarded": True}})` | `users` | Partial update |
| E1 | `insert_one({event: "onboarding_completed", ...})` | `analytics_events` | Insert |
| P5 | `find_one({"user_id": user_id}, {"_id": 0})` | `profiles` | Read-back |

#### `POST /api/profile/exam-goal`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| P1/P2 | *(get_or_create_profile)* | `profiles` | Read/insert |
| P6 | `update_one({"user_id"}, {"$set": {exam_slug, ...}})` | `profiles` | Partial update |
| P5 | `find_one({"user_id"}, {"_id": 0})` | `profiles` | Read-back |

---

### WORDS / KNOWLEDGE GRAPH ROUTES

#### `GET /api/words` (list_words — most complex query)

| # | MongoDB Operation | Collection | Pattern | Complexity |
|---|---|---|---|---|
| W1 | `count_documents({"status":"PUBLISHED", ...filters})` | `words` | Count with dynamic filter | Medium |
| W2 | `find(q, {"_id":0}).sort("headword",1).skip(offset).limit(limit)` | `words` | **Paginated sorted query with optional $or/$regex** | 🔥 HIGH |
| W3 | `find({"user_id": uid}, {"_id":0,"word_id":1}).to_list(1000)` | `saved_words` | Read all saved IDs | Low |
| W4 | `find({"user_id": uid}, {"_id":0}).to_list(2000)` | `user_word_progress` | Read ALL user progress | Medium |

**Filter variations in W2 (all possible):**
- `status = "PUBLISHED"` — always present
- `$or: [{headword: {$regex: search, $options: "i"}}, {simple_definition: {$regex: search, $options: "i"}}]` — when `search` param present
- `topic = topic` — when topic param present
- `cefr = cefr` — when cefr param present  
- `exam_relevance = exam` — when exam param present (**array containment check**)

#### `GET /api/words/{word_id}` (word_detail)

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| W5 | `find_one({"id": word_id}, {"_id": 0})` | `words` | Point read |
| G1–G4 | `build_word_graph(db, w)` — *see graph_service section* | `words` | Multiple point reads |
| W6 | `find({"slug": {"$in": exam_relevance_array}}, {"_id": 0}).to_list(20)` | `exams` | `$in` lookup |
| W7 | `find_one({"user_id": uid, "word_id": word_id})` | `saved_words` | Point read |
| W8 | `find_one({"user_id": uid, "word_id": word_id}, {"_id": 0})` | `user_word_progress` | Point read |
| E1 | `insert_one({event: "word_viewed"})` | `analytics_events` | Insert |

#### `POST /api/words/{word_id}/save`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| W9 | `find_one({"id": word_id})` | `words` | Existence check |
| W10 | `update_one(filter, {"$set": {user_id, word_id, created_at}}, upsert=True)` | `saved_words` | **Upsert** |
| E1 | *(analytics)* | `analytics_events` | Insert |

#### `DELETE /api/words/{word_id}/save`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| W11 | `delete_one({"user_id": uid, "word_id": word_id})` | `saved_words` | Delete |

#### `GET /api/saved`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| W12 | `find({"user_id": uid}).sort("created_at", -1).to_list(500)` | `saved_words` | Sorted read |
| W13 | `find({"id": {"$in": ids}}, {"_id": 0}).to_list(500)` | `words` | `$in` read |

---

### TOPICS / EXAMS ROUTES

#### `GET /api/topics`

| # | MongoDB Operation | Collection | Pattern | Risk |
|---|---|---|---|---|
| T1 | `find({}, {"_id": 0}).to_list(100)` | `topics` | Full table scan | Low |
| T2 | `count_documents({"topic": slug, "status": "PUBLISHED"})` **×N (N=6)** | `words` | **N+1 loop** | ⚠️ |

#### `GET /api/exams`

| # | MongoDB Operation | Collection | Pattern | Risk |
|---|---|---|---|---|
| T3 | `find({}, {"_id": 0}).to_list(100)` | `exams` | Full table scan | Low |
| P1/P2 | *(get_or_create_profile)* | `profiles` | Read/insert | Low |
| T4 | `count_documents({"exam_relevance": slug, "status": "PUBLISHED"})` **×N (N=6)** | `words` | **N+1 array containment count loop** | ⚠️ |

#### `GET /api/exams/{slug}`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| T5 | `find_one({"slug": slug}, {"_id": 0})` | `exams` | Point read |
| T6 | `find({"exam_relevance": slug, "status": "PUBLISHED"}, {"_id": 0}).to_list(500)` | `words` | Array containment filter |
| W4 | `find({"user_id": uid}, {"_id": 0}).to_list(2000)` | `user_word_progress` | All user progress |
| P1/P2 | *(get_or_create_profile)* | `profiles` | Read/insert |

---

### MISSION / PRACTICE ROUTES

#### `select_mission_words` ← called by /mission and /practice/start

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| P1/P2 | *(get_or_create_profile)* | `profiles` | Read/insert |
| M1 | `find({"user_id": uid}, {"_id": 0}).to_list(3000)` | `user_word_progress` | All user progress |
| M2 | `find({"id": {"$in": due_word_ids}}, {"_id": 0}).to_list(3000)` | `words` | `$in` read for due words |
| M3 | `find({"status":"PUBLISHED", "id": {"$nin": seen_ids}, ...}, {"_id": 0}).to_list(500)` | `words` | **`$nin` filter** |

#### `GET /api/mission`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| *(select_mission_words)* | — | — | — |
| MC1 | `find({"user_id": uid, "status": {"$in": ["LEARNING","RECALLING"]}}).sort("last_reviewed_at", -1).to_list(1)` | `user_word_progress` | **`$in` status filter + sort + limit 1** |
| MC2 | `find_one({"id": recent_word_id}, {"_id": 0})` | `words` | Point read |

#### `POST /api/practice/start`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| *(select_mission_words)* | — | — | for source=="mission" |
| PS1 | `find({"exam_relevance": ref, "status": "PUBLISHED"}, {"_id": 0, "id": 1}).to_list(100)` | `words` | Array containment |
| PS2 | `find({"topic": ref, "status": "PUBLISHED"}, {"_id": 0, "id": 1}).to_list(100)` | `words` | Equality filter |
| PS3 | `find_one({"id": tk}, {"_id": 1})` ×N tokens | `words` | Existence check loop |
| PS4 | `find({"user_id": uid}, {"_id": 0}).to_list(100)` | `saved_words` | for source=="saved" |
| PS5 | `find({"user_id": uid, "word_id": {"$in": word_ids}}, {"_id": 0}).to_list(1000)` | `user_word_progress` | `$in` filter |
| AC1 | `find({"status": "PUBLISHED"}, {"_id": 0}).to_list(1000)` | `words` | **FULL TABLE SCAN** (all_words_cache) |
| E1 | *(analytics)* | `analytics_events` | Insert |

#### `POST /api/practice/answer`

| # | MongoDB Operation | Collection | Pattern | Risk |
|---|---|---|---|---|
| PA1 | `find_one({"user_id": uid, "word_id": word_id}, {"_id": 0})` | `user_word_progress` | Point read |
| PA2 | `find_one({"id": word_id}, {"_id": 0})` | `words` | Point read |
| PA3 | `update_one(filter, {"$set": updated_full}, upsert=True)` | `user_word_progress` | **Upsert full doc** |
| PA4 | `update_one({"user_id": uid}, {"$inc": {"xp": xp_gain}})` | `profiles` | 🔥 **`$inc` — atomic increment** |
| PA5 | `update_one({"user_id": uid}, {"$inc": {"xp": xp_gain}})` | `users` | 🔥 **`$inc` — atomic increment** |
| E1×2 | *(analytics)* | `analytics_events` | Insert ×2 |

#### `POST /api/practice/complete`

| # | MongoDB Operation | Collection | Pattern | Risk |
|---|---|---|---|---|
| P1/P2 | *(get_or_create_profile)* | `profiles` | Read/insert | |
| PC1 | `update_one({"user_id": uid}, {"$set": {streak, longest_streak, last_active_date}})` | `profiles` | Update | |
| PC2 | `update_one({"user_id": uid}, {"$set": {"streak": streak}})` | `users` | Update | |
| PC3 | `insert_one({user_id, answered, correct, duration_ms, source, created_at})` | `study_sessions` | Insert | 🔥 Streak + insert should be atomic |
| E1 | *(analytics)* | `analytics_events` | Insert | |

---

### PROGRESS ROUTE

#### `GET /api/progress`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| P1/P2 | *(get_or_create_profile)* | `profiles` | Read/insert |
| PR1 | `find({"user_id": uid}, {"_id": 0}).to_list(5000)` | `user_word_progress` | **All user progress** |
| PR2 | `find({}, {"_id": 0, "id": 1, "topic": 1}).to_list(2000)` | `words` | **Partial field scan** |
| PR3 | `find({"user_id": uid}, {"_id": 0}).to_list(1000)` | `study_sessions` | All sessions |

---

### ANALYTICS ROUTE

#### `log_event` ← called by 15+ routes

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| E1 | `insert_one({user_id, event, props, created_at})` | `analytics_events` | Insert (fire-and-forget) |

---

### ENTITLEMENTS / SUBSCRIPTIONS

#### `ai_coach_used_today` ← called by /entitlements and /words/{id}/ai-coach

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| AU1 | `count_documents({"user_id": uid, "date": today_str})` | `ai_coach_usage` | Count with date filter |

#### `POST /api/subscription/activate`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| S1 | `update_one({"user_id": uid}, {"$set": {"tier": "pro"}})` | `users` | Update |
| S2 | `update_one({"user_id": uid}, {"$set": {...}}, upsert=True)` | `subscriptions` | Upsert |
| E1 | *(analytics)* | `analytics_events` | Insert |

#### `POST /api/subscription/cancel`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| S3 | `update_one({"user_id": uid}, {"$set": {"tier": "free"}})` | `users` | Update |
| S4 | `update_one({"user_id": uid}, {"$set": {"status": "cancelled"}})` | `subscriptions` | Update |
| E1 | *(analytics)* | `analytics_events` | Insert |

---

### TTS / AUDIO

#### `make_tts` (called by `/words/{id}/audio` when no external audio found)

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| TTS1 | `find_one({"key": key}, {"_id": 1})` | `tts_cache` | Cache existence check |
| TTS2 | `insert_one({"key": key, "audio": bytes, "created_at": ...})` | `tts_cache` | Insert binary |

#### `GET /api/tts/{key}.mp3`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| TTS3 | `find_one({"key": key})` | `tts_cache` | Point read, returns BSON Binary |

#### `GET /api/words/{word_id}/audio`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| W5 | `find_one({"id": word_id}, {"_id": 0})` | `words` | Point read |
| AU2 | `update_one({"id": word_id}, {"$set": {"audio": audio_dict}})` | `words` | Update JSONB field |

---

### AI COACH

#### `POST /api/words/{word_id}/ai-coach`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| W5 | `find_one({"id": word_id}, {"_id": 0})` | `words` | Point read |
| AI1 | `find_one({"word_id": word_id}, {"_id": 0})` | `ai_coach_content` | Cache check |
| AI2 | `insert_one({word_id, content, provenance, status, created_at})` | `ai_coach_content` | Insert |
| AI3 | `insert_one({user_id, word_id, date, created_at})` | `ai_coach_usage` | Insert |
| E1 | *(analytics)* | `analytics_events` | Insert |

---

### ARTICLES

#### `GET /api/articles`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| AR1 | `find(q, {"_id": 0, "body": 0}).to_list(100)` | `articles` | Partial projection (body excluded) |

#### `GET /api/articles/{article_id}`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| AR2 | `find_one({"id": article_id}, {"_id": 0})` | `articles` | Point read |

---

### SMART REVIEW / LOOKUP / IMPORT

#### `GET /api/review/slipping`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| SR1 | `find({"user_id": uid, "status": {"$in": ["SEEN","LEARNING","RECALLING"]}}).to_list(3000)` | `user_word_progress` | `$in` status filter |
| SR2 | `find({"user_id": uid, "word_id": {"$in": ids}}).to_list(100)` | `user_word_progress` | `$in` |
| SR3 | `find({"id": {"$in": ids}}).to_list(100)` | `words` | `$in` |

#### `GET /api/lookup`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| L1 | `find_one({"headword": norm})` | `words` | Exact headword lookup |
| L2 | `find_one({"user_id": uid, "word_id": w["id"]})` | `saved_words` | Point read |

#### `POST /api/words/import` → `ensure_word`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| EW1 | `find_one({"$or": [{"canonical_key": ckey}, {"headword": norm}]}, {"_id": 0, "id": 1})` | `words` | **`$or` with two fields** |
| + `ingest_word` | *(see content_ingest section)* | | |

#### `POST /api/extract` / `POST /api/extract-pdf` → `classify_words`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| CW1 | `find({"headword": {"$in": candidates}}).to_list(200)` | `words` | `$in` on headword |
| CW2 | `find({"user_id": uid, "word_id": {"$in": ids}}).to_list(500)` | `user_word_progress` | `$in` |

#### `POST /api/practice/build`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| PS3 | `find_one({"id": token}, {"_id": 1})` ×N | `words` | Existence check loop |
| AC1 | `find({"status":"PUBLISHED"}).to_list(1000)` | `words` | Full table scan (all_words_cache) |
| PS5 | `find({"user_id": uid, "word_id": {"$in": resolved}}).to_list(200)` | `user_word_progress` | `$in` |
| E1 | *(analytics)* | `analytics_events` | Insert |

---

### GRAPH SERVICE (called by word_detail and startup)

#### `build_word_graph` ← called by `GET /api/words/{word_id}`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| G1 | `find_one({"id": ref, "status":"PUBLISHED"}, projection)` | `words` | Point read per relation entry |
| G2 | `find_one({"status":"PUBLISHED", "$or": [{"canonical_key": hw_key}, {"headword": hw}]}, projection)` | `words` | **`$or` + `AND`** per unresolved entry |

⚠️ **ASSUMPTION:** A typical word has ~5–15 relations. G1/G2 runs per relation entry. For a word with 12 relations, this is up to 24 individual DB queries in a single request.

#### `load_id_by_key` ← called by startup and content_ingest

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| GS1 | `find({}, {"_id":0, "id":1, "headword":1}).to_list(200000)` | `words` | Full scan (id+headword only) |

#### `resolve_all_relationship_refs` ← called at STARTUP

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| GS2 | `find({}, {"_id":0}).to_list(200000)` | `words` | Full scan |
| GS3 | `update_one({"id": w["id"]}, {"$set": {"relations": normalized}})` ×N | `words` | Update per word if changed |

#### `refresh_refs_for_new_key` ← called by `ingest_word`

| # | MongoDB Operation | Collection | Pattern | Risk |
|---|---|---|---|---|
| GS4 | `find({"$or": [{f"relations.{f}.headword": ckey} for f in FIELDS]}, {"_id":0}).to_list(5000)` | `words` | **Nested JSONB array field `$or` — most complex query** | 🔥 |
| GS5 | `update_one({"id": w["id"]}, {"$set": {"relations": rels}})` ×N | `words` | Conditional update per word |

---

### CONTENT INGEST (called by import + startup)

#### `_load_context` ← called by ingest_word, bulk_ingest, quality_report

| # | MongoDB Operation | Collection |
|---|---|---|
| CI1 | `find({}, {"_id":0, "id":1, "headword":1}).to_list(200000)` | `words` |
| CI2 | `find({}, {"_id":0, "slug":1}).to_list(1000)` | `exams` |

#### `ingest_word`

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| CI3 | `update_one({"id": wid}, {"$set": doc}, upsert=True)` | `words` | Upsert full canonical doc |

#### `migrate_content_lifecycle` ← called at STARTUP

| # | MongoDB Operation | Collection | Pattern |
|---|---|---|---|
| CI4 | `find({"lifecycle_version": {"$ne": 1}}, {"_id":0}).to_list(200000)` | `words` | **`$ne` filter** |
| CI5 | `update_one({"id": w["id"]}, {"$set": update})` ×N | `words` | Conditional update per word |

---

### STARTUP SEQUENCE (runs on every backend restart)

| # | MongoDB Operation | Notes |
|---|---|---|
| ST1 | `db.words.count_documents({})` | Seed guard |
| ST2 | `db.words.insert_many(docs)` | Bulk seed insert |
| ST3 | `db.topics.count_documents({})` | Seed guard |
| ST4 | `db.topics.insert_many([...])` | Bulk seed insert |
| ST5 | `db.exams.count_documents({})` | Seed guard |
| ST6 | `db.exams.insert_many([...])` | Bulk seed insert |
| ST7 | `db.articles.count_documents({})` | Seed guard |
| ST8 | `db.articles.insert_many([...])` | Bulk seed insert |
| ST9 | `db.words.find_one({"id": wid}, {"_id":1})` ×N | Word bank upsert guard loop |
| ST10 | `db.words.update_one({"id":wid}, {"$set":{...}}, upsert=True)` ×N | Word bank upsert |
| ST11 | `db.words.find({}, {"_id":0}).to_list(200000)` | `migrate_canonical` — all words |
| ST12 | `db.words.update_one({"id": w["id"]}, {"$set": canonical})` ×N | Per-word canonical migration |
| ST13 | `db.words.create_index("canonical_key", unique=True)` | Index creation |
| + many more `create_index` calls | Various collections | **Must be removed for Supabase** |

---

## Part 3 — MongoDB → Supabase/PostgreSQL Translation Map

### 3A — Read Operations

| MongoDB | Supabase Python (supabase v2.31.0 async) | Notes |
|---|---|---|
| `find_one({"field": val})` | `.table(t).select("*").eq("field", val).maybe_single().execute()` | Returns `None` on no match |
| `find_one({"f": val}, {"_id":0, "a":1, "b":1})` | `.table(t).select("a,b").eq("f", val).maybe_single().execute()` | Field projection → select columns |
| `find({"f": val}).to_list(n)` | `.table(t).select("*").eq("f", val).limit(n).execute()` | Returns list in `.data` |
| `find({}).to_list(n)` | `.table(t).select("*").limit(n).execute()` | |
| `find(q).sort("field", 1).skip(offset).limit(n)` | `.table(t).select("*").<filters>.order("field", desc=False).range(offset, offset+n-1).execute()` | `range()` is inclusive |
| `find(q).sort("field", -1).to_list(1)` | `.table(t).select("*").<filters>.order("field", desc=True).limit(1).execute()` | |
| `count_documents(q)` | `.table(t).select("*", count="exact").eq(...).execute()` → `.count` | Returns int in `.count` |

### 3B — Filter Operators

| MongoDB | Supabase | Notes |
|---|---|---|
| `{"field": val}` | `.eq("field", val)` | Exact match |
| `{"field": {"$ne": val}}` | `.neq("field", val)` | Not equal |
| `{"field": {"$in": [a,b,c]}}` | `.in_("field", [a,b,c])` | In array |
| `{"field": {"$nin": [a,b,c]}}` | `.not_("field", "in", f"({','.join(map(str,vals))})")` | Not in |
| `{"field": {"$regex": s, "$options": "i"}}` | `.ilike("field", f"%{s}%")` | ✅ GIN trigram index supports this |
| `{"$or": [{...}, {...}]}` | `.or_("cond1,cond2")` | PostgREST OR syntax |
| `{"a": x, "$or": [{...}]}` | `.eq("a", x).or_("...")` | AND + OR |
| `{"field": {"$in": list}}` (array field containment) | `.contains("field", [val])` | For TEXT[] array columns |
| `{"array_field": val}` (MongoDB checks if array contains val) | `.contains("array_field", [val])` | e.g. `exam_relevance` |

### 3C — Write Operations

| MongoDB | Supabase | Notes |
|---|---|---|
| `insert_one({...})` | `.table(t).insert({...}).execute()` | |
| `insert_many([...])` | `.table(t).insert([...]).execute()` | Batch insert |
| `update_one({"f":v}, {"$set": {...}})` | `.table(t).update({...}).eq("f", v).execute()` | Only listed fields |
| `update_one(filter, doc, upsert=True)` | `.table(t).upsert({...}).execute()` | Entire row; PK must be in doc |
| `update_one({"f":v}, {"$set": partial}, upsert=True)` where partial ≠ full row | `.table(t).upsert({pk, ...partial}).execute()` | ⚠️ Must include PK + all required NOT NULL cols |
| `delete_one({"f": v})` | `.table(t).delete().eq("f", v).execute()` | Deletes ALL matching rows — **add `.limit(1)` if needed** |
| `$inc: {"xp": n}` | ❌ **NOT SUPPORTED** in supabase-py | 🔥 Requires PostgreSQL RPC function |

### 3D — Special MongoDB Behaviors

| Feature | MongoDB Behavior | Supabase/PostgreSQL | Action Required |
|---|---|---|---|
| `$inc` | Atomic server-side increment | **No native equivalent in PostgREST** | 🔥 Create RPC function `increment_xp(user_id, amount)` |
| TTL index on `expires_at` | Auto-deletes expired documents | **No equivalent** | ❌ Must implement cleanup separately |
| `_id` field | Auto-generated ObjectId | BIGSERIAL `id` auto-generated | No action needed |
| BSON Binary (`tts_cache.audio`) | Stored as Binary | PostgreSQL `BYTEA` | supabase-py handles `bytes` ↔ BYTEA ✅ |
| `$or` on nested JSONB array fields | `relations.{field}.headword` | `jsonb_path_exists()` or SQL RPC | 🔥 Must use RPC for `refresh_refs_for_new_key` |
| Startup `create_index` | Creates indexes on startup | Indexes already in SQL migrations | Remove all `create_index` calls from startup |
| `{"_id": 0}` projection | Excludes `_id` | Not needed (no `_id` in Supabase) | Remove all projection dicts |

---

## Part 4 — MongoDB-Specific Behavior Requiring Special Handling

### 4A — `$inc` Atomic Increment (🔥 Critical)

**Affected code:** `practice/answer` (PA4, PA5) — XP on both `profiles` and `users`

**Problem:** MongoDB's `$inc` is a server-side atomic operation. supabase-py has no equivalent. A read-then-write (read XP → add N → write) introduces a race condition: two simultaneous `/practice/answer` calls for the same user could both read `xp=100`, both compute `110`, and the final value would be `110` instead of `120`.

**Required solution (🔷 PROPOSED):** Create a PostgreSQL stored procedure:
```sql
CREATE OR REPLACE FUNCTION public.increment_user_xp(p_user_id TEXT, p_amount INTEGER)
RETURNS VOID LANGUAGE sql AS $$
  UPDATE users   SET xp = xp + p_amount WHERE user_id = p_user_id;
  UPDATE profiles SET xp = xp + p_amount WHERE user_id = p_user_id;
$$;
```
Called via: `sb.rpc("increment_user_xp", {"p_user_id": uid, "p_amount": xp_gain}).execute()`

### 4B — Session TTL Cleanup (❌ Unresolved)

**Affected collection:** `user_sessions`

**MongoDB behavior:** TTL index `expireAfterSeconds=0` on `expires_at` automatically purges expired documents.

**Supabase behavior:** No equivalent. Expired sessions will accumulate indefinitely.

**Options (🔷 PROPOSED — decision needed):**
1. pg_cron (available in Supabase): Schedule `DELETE FROM user_sessions WHERE expires_at < now()` daily
2. Application-level: Add cleanup on login/startup (delete WHERE expires_at < now() for that user)
3. Edge Function scheduled job

**Risk if unresolved:** Table bloat; no security risk because `get_current_user` already checks `expires_at`.

### 4C — `$nin` (Not-In) for New Word Selection (select_mission_words)

**MongoDB:** `{"id": {"$nin": list(seen_ids)}}` where `seen_ids` can be up to 3,000 IDs.

**Supabase PostgREST:** `.not_("id", "in", "(id1,id2,...)")` — URL length limit could be hit with 3,000+ IDs.

**⚠️ ASSUMPTION:** This is a potential issue. Current word bank = 231 words, seen_ids ≤ 231. At this scale, URL limits are not a problem. At 10,000+ words it becomes risky.

**Safer alternative (🔷 PROPOSED):**
```python
# Use a LEFT JOIN via RPC instead of $nin
# Or: Fetch all published words, filter in Python
all_published = sb.table("words").select("id,headword,topic,...").eq("status","PUBLISHED").execute()
candidates = [w for w in all_published.data if w["id"] not in seen_ids]
```
This is consistent with `all_words_cache()` pattern already used in `practice/start`.

### 4D — `refresh_refs_for_new_key` — Nested JSONB Array `$or` (🔥 Complex)

**MongoDB query:**
```python
or_clauses = [{f"relations.{f}.headword": ckey} for f in ["synonyms","antonyms","related","confusing_words"]]
db.words.find({"$or": or_clauses}, {"_id": 0}).to_list(5000)
```
This queries MongoDB for documents where ANY of the nested arrays inside the `relations` JSONB object contains an object with `headword == ckey`.

**PostgreSQL equivalent requires jsonb_path_exists or a generated expression:**
```sql
WHERE jsonb_path_exists(relations, '$.synonyms[*].headword ? (@ == $headword)', jsonb_build_object('headword', $1))
   OR jsonb_path_exists(relations, '$.antonyms[*].headword ? (@ == $headword)', jsonb_build_object('headword', $1))
   ...
```

**⚠️ ASSUMPTION:** The GIN index on `relations` may or may not accelerate this `jsonb_path_exists` query — needs performance testing.

**Required solution (🔷 PROPOSED):** Create a PostgreSQL RPC:
```sql
CREATE OR REPLACE FUNCTION public.find_words_with_unresolved_relation(p_headword TEXT)
RETURNS SETOF public.words LANGUAGE sql AS $$
  SELECT * FROM public.words
  WHERE jsonb_path_exists(relations, '$.synonyms[*].headword ? (@ == $hw)', jsonb_build_object('hw', p_headword))
     OR jsonb_path_exists(relations, '$.antonyms[*].headword ? (@ == $hw)', jsonb_build_object('hw', p_headword))
     OR jsonb_path_exists(relations, '$.related[*].headword ? (@ == $hw)', jsonb_build_object('hw', p_headword))
     OR jsonb_path_exists(relations, '$.confusing_words[*].headword ? (@ == $hw)', jsonb_build_object('hw', p_headword));
$$;
```

### 4E — Startup Code (⚠️ Must refactor)

The `startup()` function currently:
- Creates MongoDB indexes (`create_index`) — must be removed
- Runs seed/migration logic — must be refactored to Supabase equivalents
- `seed_content()` guards with `count_documents({}) == 0` — fine, maps to Supabase count check
- `migrate_canonical()` runs full word scan + updates — very slow for large word banks; ok for 231 words
- `resolve_all_relationship_refs()` runs full scan + per-word updates — must use Supabase

### 4F — `all_words_cache()` — Full Table Scan on Every Practice Start

**MongoDB:** `db.words.find({"status": "PUBLISHED"}, {"_id": 0}).to_list(1000)` — loads all 231 published words into memory on every `/practice/start` call.

**Supabase:** `sb.table("words").select("*").eq("status","PUBLISHED").execute()` — works but each call incurs HTTP round-trip to Supabase.

**⚠️ ASSUMPTION:** At 231 words this is fast (<100ms). At 2,000+ words this becomes a noticeable latency source.

**🔷 PROPOSED:** Add a simple in-process TTL cache (e.g., 60-second expiry) for the published words list using Python `functools.lru_cache` with timestamp check. This is a code pattern change, not a schema change.

---

## Part 5 — Supabase Schema Gaps

After comparing every MongoDB operation against the `000_consolidated_migration.sql` + `008_add_source_mongo_id.sql`:

| Gap | Severity | Details |
|---|---|---|
| No `increment_xp` RPC function | 🔥 HIGH | Needed for atomic `$inc` replacement |
| No session TTL cleanup | MEDIUM | Expired sessions accumulate |
| No `find_words_with_unresolved_relation` RPC | MEDIUM | Needed for `refresh_refs_for_new_key` |
| `study_sessions` missing `source_mongo_id` for NEW records | LOW | New app-generated records have NULL — this is by design ✅ |
| `user_sessions` has `BIGSERIAL id` but MongoDB had no `id` field | LOW | Not a problem; `session_token` is the actual key |

**All 15 tables are present. All required columns are present. All required indexes are present (trigram indexes for ILIKE confirmed in migration 007 preflight correction).**

**✅ CONFIRMED: No missing tables or columns relative to the MongoDB operation inventory.**

---

## Part 6 — Translation Reference Tables

### 6A — Search / Regex

| MongoDB | Supabase | Index Used |
|---|---|---|
| `{"headword": {"$regex": s, "$options": "i"}}` | `.ilike("headword", f"%{s}%")` | `words_headword_trgm_idx` (GIN) ✅ |
| `{"simple_definition": {"$regex": s, "$options": "i"}}` | `.ilike("simple_definition", f"%{s}%")` | `words_definition_trgm_idx` (GIN) ✅ |
| `{"$or": [headword regex, definition regex]}` | `.or_("headword.ilike.%{s}%,simple_definition.ilike.%{s}%")` | Both trgm indexes ✅ |

### 6B — Pagination and Sorting

| MongoDB | Supabase |
|---|---|
| `.sort("headword", 1)` | `.order("headword", desc=False)` |
| `.sort("created_at", -1)` | `.order("created_at", desc=True)` |
| `.sort("last_reviewed_at", -1)` | `.order("last_reviewed_at", desc=True)` |
| `.skip(offset).limit(limit)` | `.range(offset, offset + limit - 1)` |
| `.limit(1)` only | `.limit(1).maybe_single()` |

### 6C — Date / Timestamp

| Context | MongoDB | Supabase |
|---|---|---|
| Storing | `datetime` objects | ISO 8601 string `"2026-06-27T10:00:00+00:00"` |
| `exam_date` | ISO string `"2026-06-27"` | `DATE` column, pass string `"2026-06-27"` |
| `ai_coach_usage.date` | `date.today().isoformat()` string | `DATE` column, pass string directly |
| `profiles.last_active_date` | ISO date string | `DATE` column |
| Querying by date | `{"date": today_str}` | `.eq("date", today_str)` ✅ |
| `timedelta` arithmetic | Python `datetime +/- timedelta` | Same in Python; store as ISO string |

### 6D — Arrays (TEXT[])

| Column | MongoDB | Supabase |
|---|---|---|
| `exam_relevance` | Array field; `{"exam_relevance": slug}` checks containment | `.contains("exam_relevance", [slug])` |
| `{"exam_relevance": {"$in": list_of_slugs}}` for exams lookup | Query `exams` by slug IN list | `.in_("slug", list_of_slugs)` ✅ |
| `synonyms`, `antonyms` etc. | `TEXT[]` lists | `TEXT[]` in Postgres; pass Python `list` |
| `recent_results` | `[1,0,1,1,...]` | `SMALLINT[]` in Postgres; pass Python `list` ✅ |
| `last_reason_codes` | `["reason1","reason2"]` | `TEXT[]`; pass Python `list` ✅ |

### 6E — JSONB Fields

| Column | MongoDB | Supabase |
|---|---|---|
| `words.relations` | Dict of lists of dicts `{"synonyms": [{"ref":"...", "headword":"..."}]}` | `JSONB`; supabase-py serializes Python dict automatically ✅ |
| `words.audio` | Dict `{"us_url":"...", "uk_url":"...", "tts_url":"..."}` | `JSONB` ✅ |
| `words.meanings` | JSONB ✅ | `JSONB` ✅ |
| `ai_coach_content.content` | Dict `{explanation, example, mnemonic}` | `JSONB NOT NULL` ✅ |
| `analytics_events.props` | Dict | `JSONB NOT NULL DEFAULT '{}'` ✅ |

### 6F — Binary Data (TTS Cache)

| MongoDB | Supabase |
|---|---|
| `BSON Binary` stored in `tts_cache.audio` | `BYTEA NOT NULL` in PostgreSQL |
| `bytes(doc["audio"])` to read | supabase-py returns Python `bytes` from BYTEA ✅ |
| Insert: `{"audio": audio_bytes}` where `audio_bytes` is `bytes` | Insert: same `bytes` object — supabase-py serializes to BYTEA ✅ |

---

## Part 7 — Authentication Dependencies

### ✅ CONFIRMED: Auth system is FULLY CUSTOM and UNCHANGED for Stage 3.

| Component | Current (MongoDB) | After Stage 3 (Supabase) |
|---|---|---|
| Password storage | `bcrypt` via `passlib` | Same — unchanged |
| `user_id` format | `"user_" + secrets.token_hex(6)` TEXT | Same — unchanged |
| Session token | `secrets.token_urlsafe(32)` in `user_sessions` | Same — stored in `public.user_sessions` |
| Session check | `db.user_sessions.find_one(session_token)` | `sb.table("user_sessions").select(...).eq("session_token", token).maybe_single()` |
| Google OAuth | Emergent session service → custom user creation | Same — unchanged |
| Supabase Auth (auth.users) | NOT USED | NOT USED |
| RLS | Disabled (migration created schema only) | Remains disabled |

**⚠️ ASSUMPTION:** If RLS is ever enabled in the future, ALL backend operations use `service_role_key` which bypasses RLS regardless. Frontend should never be given the service_role_key.

**`get_current_user` dependency — critical auth path:**  
Every authenticated request calls A1 + A2. These two queries run on every authenticated API call. In MongoDB they are indexed point reads. In Supabase they will use `session_token` unique index and `user_id` PK respectively — equivalent performance expected.

---

## Part 8 — Repository Architecture Proposal

### 🔷 PROPOSED: Environment-Switched Repository Pattern

**Design goal:** Zero application logic changes. All MongoDB calls in `server.py` and service files are replaced by calls to a thin repository layer. The repository has two implementations: MongoDB (current) and Supabase (new). The active implementation is selected by an environment variable.

**Proposed file structure:**
```
/app/backend/
├── db/
│   ├── __init__.py           # exports: get_db() → DatabaseRepository
│   ├── base.py               # Abstract base class / type definitions
│   ├── mongo_repo.py         # Current Motor implementation (exact copy of current db.* calls)
│   └── supabase_repo.py      # New Supabase async implementation
└── server.py                 # Calls repo.method() instead of db.*
```

**Environment variable gate:**
```
DB_BACKEND=supabase    # switches to Supabase
DB_BACKEND=mongo       # (default) stays on MongoDB
```

**Interface example (not for implementation yet — proposed only):**
```python
class DatabaseRepository(Protocol):
    async def get_user_by_email(self, email: str) -> Optional[dict]: ...
    async def get_user_by_id(self, user_id: str) -> Optional[dict]: ...
    async def create_user(self, user_doc: dict) -> None: ...
    async def get_session(self, token: str) -> Optional[dict]: ...
    async def create_session(self, session_doc: dict) -> None: ...
    async def delete_session(self, token: str) -> None: ...
    # ... 60+ more methods
```

**Key architectural decision needed (❌ UNRESOLVED):**  
How granular should the repository interface be? Two options:
- **Option A: Thin collection-level wrapper** — Each method maps 1:1 to a MongoDB collection operation. Lower abstraction. Faster to implement.
- **Option B: Domain-level methods** — Each method maps to a business operation (e.g., `record_practice_answer` that handles progress upsert + XP increment in one call). Better encapsulation for atomic operations. More design work.

**Recommendation:** Option B for operations involving `$inc` or multiple collections atomically (practice/answer, practice/complete, subscription activate/cancel). Option A for all single-collection reads. This is a hybrid approach.

### 🔷 Required PostgreSQL RPC Functions (must be created in Supabase before Stage 3 implementation)

```sql
-- 1. Atomic XP increment (replaces $inc)
CREATE OR REPLACE FUNCTION public.increment_user_xp(p_user_id TEXT, p_amount INTEGER)
RETURNS VOID LANGUAGE sql AS $$
  UPDATE public.users    SET xp = xp + p_amount, updated_at = now() WHERE user_id = p_user_id;
  UPDATE public.profiles SET xp = xp + p_amount, updated_at = now() WHERE user_id = p_user_id;
$$;

-- 2. Find words with unresolved relation refs (replaces complex $or on JSONB)
CREATE OR REPLACE FUNCTION public.find_words_with_relation_headword(p_headword TEXT)
RETURNS SETOF public.words LANGUAGE sql STABLE AS $$
  SELECT * FROM public.words
  WHERE jsonb_path_exists(relations, '$.synonyms[*].headword ? (@ == $hw)', jsonb_build_object('hw', p_headword))
     OR jsonb_path_exists(relations, '$.antonyms[*].headword ? (@ == $hw)', jsonb_build_object('hw', p_headword))
     OR jsonb_path_exists(relations, '$.related[*].headword ? (@ == $hw)', jsonb_build_object('hw', p_headword))
     OR jsonb_path_exists(relations, '$.confusing_words[*].headword ? (@ == $hw)', jsonb_build_object('hw', p_headword));
$$;

-- 3. Session cleanup (replaces TTL index)
CREATE OR REPLACE FUNCTION public.purge_expired_sessions()
RETURNS INTEGER LANGUAGE sql AS $$
  WITH deleted AS (
    DELETE FROM public.user_sessions WHERE expires_at < now() RETURNING id
  )
  SELECT COUNT(*)::INTEGER FROM deleted;
$$;
```

---

## Part 9 — Safe Rollback Architecture

### 🔷 PROPOSED: Feature-Flag Rollback (Zero-Downtime)

**Mechanism:**  
A single environment variable `DB_BACKEND` controls which database client is active.

**Rollback procedure (if Supabase implementation fails after switchover):**

```
Step 1: SET DB_BACKEND=mongo in /app/backend/.env
Step 2: sudo supervisorctl restart backend
Step 3: Verify GET /api/auth/me returns 200
Step 4: Verify GET /api/words returns data
Total estimated time: < 2 minutes
```

**Why this is safe:**  
- MongoDB data was never modified during the switchover (Stage 2 was read-only)
- MongoDB data has been continuously accepting live writes throughout Stages 1–3
- The Supabase data is a snapshot from before Stage 3; it may be stale (new MongoDB writes post-migration not in Supabase)
- **Rolling back to MongoDB means zero data loss**

**Data divergence risk (⚠️ ASSUMPTION):**  
Once the application switches to Supabase (`DB_BACKEND=supabase`), new data is written to Supabase only. Rolling back to MongoDB at that point means MongoDB is missing all data written during the Supabase period. This is a **one-way door** — once Stage 3 is live in production with real users, rollback to MongoDB will cause data loss for those new records.

**Mitigation:** After `DB_BACKEND=supabase` goes live, the MongoDB rollback window is approximately 48–72 hours before divergence becomes practically unrecoverable. Plan a post-switchover observation period and define a hard cutoff time for the rollback window.

### Operations That Must Not Be Split Across DB Backends

When running `DB_BACKEND=supabase`, ALL operations go to Supabase. There is no hybrid mode where some operations go to MongoDB and some to Supabase. The repository pattern enforces this at initialization.

---

## Part 10 — Complete Post-Switch Test Plan

### Test Environment
- Test user: `demo@vocably.app` / `demo1234`
- Backend: FastAPI on port 8001
- `DB_BACKEND=supabase` set

### Acceptance Criteria (all must pass for Stage 3 to be declared COMPLETE)

#### AC-AUTH — Authentication (all 5 must pass)

| ID | Test | Method | Pass Criteria |
|---|---|---|---|
| AUTH-1 | Register new user | POST /api/auth/register `{email, password, name}` | 201, returns `{token, user}` |
| AUTH-2 | Login with email/password | POST /api/auth/login `{email, password}` | 200, returns `{token, user}` |
| AUTH-3 | Get current user | GET /api/auth/me (Bearer token) | 200, returns correct user |
| AUTH-4 | Logout | POST /api/auth/logout | 200, `{ok: true}` |
| AUTH-5 | Reject expired/invalid token | GET /api/auth/me with invalid token | 401 |

#### AC-WORDS — Word Operations (all 7 must pass)

| ID | Test | Pass Criteria |
|---|---|---|
| WORD-1 | List words (no filter) | GET /api/words → total > 0, words array |
| WORD-2 | Search by headword | GET /api/words?search=serendip → results include "serendipity" |
| WORD-3 | Filter by topic | GET /api/words?topic=everyday → all words have topic=everyday |
| WORD-4 | Filter by exam | GET /api/words?exam=gre → exam_relevance contains gre |
| WORD-5 | Pagination | GET /api/words?limit=5&offset=5 → 5 words, offset=5 in response |
| WORD-6 | Word detail + graph | GET /api/words/{id} → word, graph, exams, saved, progress keys present |
| WORD-7 | Save and unsave | POST /api/words/{id}/save → saved:true; DELETE → saved:false; GET /api/saved → reflects change |

#### AC-PRACTICE — Practice Flow (all 7 must pass)

| ID | Test | Pass Criteria |
|---|---|---|
| PRAC-1 | Mission summary | GET /api/mission → total_words, streak, xp keys |
| PRAC-2 | Start mission practice | POST /api/practice/start?source=mission → questions array, count > 0 |
| PRAC-3 | Start exam practice | POST /api/practice/start?source=exam&ref=gre → questions from GRE words |
| PRAC-4 | Submit correct answer | POST /api/practice/answer `{word_id, mode, correct:true, response_time_ms:3000}` → xp_gain=10, status in response |
| PRAC-5 | Submit wrong answer | Same with correct:false → xp_gain=2, status in response |
| PRAC-6 | XP correctly incremented | After 3 correct answers: GET /api/progress → xp increased by 30 |
| PRAC-7 | Complete session + streak | POST /api/practice/complete `{answered:5, correct:4, duration_ms:60000}` → streak, longest_streak |

#### AC-PROGRESS — Progress and Analytics (all 3 must pass)

| ID | Test | Pass Criteria |
|---|---|---|
| PROG-1 | Full progress page | GET /api/progress → words_learned, accuracy, xp, level, streak, weak_areas |
| PROG-2 | Slipping words | GET /api/review/slipping → count, words array |
| PROG-3 | Analytics event | POST /api/analytics `{event: "test_event", props: {}}` → 200 ok |

#### AC-CONTENT — Topics, Exams, Articles (all 5 must pass)

| ID | Test | Pass Criteria |
|---|---|---|
| CONT-1 | Topics with word counts | GET /api/topics → topics with word_count > 0 |
| CONT-2 | Exams list | GET /api/exams → 6 exams, word_count for each |
| CONT-3 | GRE exam detail | GET /api/exams/gre → exam, words, total_words, mastered, learning |
| CONT-4 | Articles list | GET /api/articles → articles array |
| CONT-5 | Article detail | GET /api/articles/{id} → article with body |

#### AC-AI — AI Coach + TTS (all 3 must pass)

| ID | Test | Pass Criteria |
|---|---|---|
| AI-1 | AI Coach (cached) | POST /api/words/{id}/ai-coach → content with explanation, example, mnemonic; cached:true on 2nd call |
| TTS-1 | Word audio | GET /api/words/{id}/audio → us_url or tts_url present |
| TTS-2 | Serve TTS mp3 | GET /api/tts/{key}.mp3 → 200, Content-Type: audio/mpeg |

#### AC-ENTITLEMENTS (all 3 must pass)

| ID | Test | Pass Criteria |
|---|---|---|
| ENT-1 | Entitlements | GET /api/entitlements → tier, limits, ai_coach_used_today |
| ENT-2 | Subscribe | POST /api/subscription/activate → tier:pro |
| ENT-3 | Cancel | POST /api/subscription/cancel → tier:free |

#### AC-LOOKUP-IMPORT (all 3 must pass)

| ID | Test | Pass Criteria |
|---|---|---|
| LU-1 | Lookup existing word | GET /api/lookup?word=serendipity → in_bank:true |
| LU-2 | Import new word | POST /api/words/import `{headword: "ephemeral"}` → id returned |
| LU-3 | Extract from text | POST /api/extract `{text: "The ephemeral nature of happiness..."}` → known/learning/new arrays |

---

## Part 11 — Data Loss / Race Condition / Behavior Change Risk Register

| ID | Risk | Severity | Trigger | Mitigation |
|---|---|---|---|---|
| R1 | XP lost due to concurrent `/practice/answer` | 🔥 HIGH | Two answers submitted within ~50ms for same user | Use `increment_user_xp` RPC (see Part 8) |
| R2 | Streak corruption due to concurrent `/practice/complete` | MEDIUM | Two sessions completed simultaneously (unlikely) | Acceptable: wrap streak update + session insert in RPC if needed |
| R3 | Supabase `upsert` overwrites columns not in `$set` | 🔥 HIGH | `saved_words` upsert must include `user_id, word_id, created_at` — all NOT NULL columns | Verify upsert payload includes all NOT NULL columns |
| R4 | Binary TTS data (`bytes` type) breaks on roundtrip | MEDIUM | `bytes(doc["audio"])` call on data retrieved from Supabase BYTEA | Test with an actual TTS roundtrip; verify type is `bytes` |
| R5 | Expired sessions accumulate (no TTL) | LOW | Background table growth | Implement `purge_expired_sessions()` RPC (pg_cron or app-level) |
| R6 | `$nin` URL length exceeded for large word banks | LOW | Word bank grows beyond ~2,000 words | Refactor to Python-side filter using `all_words_cache()` |
| R7 | `ai_coach_content` duplicate on concurrent AI Coach calls | LOW | Two simultaneous first-time AI Coach requests for same word | Supabase `word_id UNIQUE` constraint will reject second insert gracefully |
| R8 | `user_sessions` insert concurrent race (same token) | VERY LOW | Token collision is cryptographically negligible | `session_token UNIQUE` constraint handles it |
| R9 | Data divergence after switchover if rollback needed | 🔥 HIGH (post-live) | Rollback to MongoDB after new Supabase writes | Define 48-hour rollback window; document cutoff |
| R10 | `refresh_refs_for_new_key` fails silently (unsupported `$or`) | MEDIUM | User imports a new word and existing relations don't update | Implement as RPC before enabling word import (Part 8) |

---

## Part 12 — Operations That Should Be Switched Together Transactionally

### Atomic Operation Groups (🔷 PROPOSED as PostgreSQL functions)

| Group | Operations | Reason | Solution |
|---|---|---|---|
| **XP Increment** | `UPDATE users SET xp+=n` + `UPDATE profiles SET xp+=n` | Both must succeed or neither; inconsistency confuses user-facing displays | `increment_user_xp(user_id, amount)` RPC |
| **Practice Complete** | `UPDATE profiles streak` + `UPDATE users streak` + `INSERT study_sessions` | Streak count in users/profiles must match study_sessions count | RPC or accept eventual consistency (streak update + insert rarely conflicts) |
| **Subscription Activate** | `UPDATE users tier=pro` + `UPSERT subscriptions` | If tier update succeeds but subscriptions fails, user is pro without a subscription record | Wrap in RPC or accept (both are idempotent) |
| **Register** | `INSERT users` + `INSERT user_sessions` | If session creation fails, user exists but can't log in | Retry session creation on login; acceptable eventual consistency |

### Operations That Are Independently Safe to Switch

All single-collection reads and writes are safe to switch independently:
- All analytics inserts (fire-and-forget in current code)
- All word reads (words, topics, exams, articles)
- All progress reads
- Saved words save/unsave
- AI Coach cache read/write

---

## Implementation Prerequisites Checklist

Before writing any Stage 3 implementation code, these SQL functions must be created in Supabase:

- [ ] `public.increment_user_xp(TEXT, INTEGER)` — atomic XP increment
- [ ] `public.find_words_with_relation_headword(TEXT)` — JSONB `$or` replacement
- [ ] `public.purge_expired_sessions()` — TTL cleanup
- [ ] *(Optional) Wrap practice_complete in RPC for atomic streak*

And these backend structural decisions must be resolved:

- [ ] Repository architecture: Option A (thin wrapper) vs. Option B (domain methods) vs. hybrid?
- [ ] Session TTL cleanup strategy: pg_cron vs. app-level vs. Edge Function?
- [ ] `all_words_cache()` caching strategy: in-process TTL cache?
- [ ] Rollback window: How many hours after go-live is MongoDB rollback allowed?

---

## Summary Table: Stage 3 Complexity by Collection

| Collection | Read Complexity | Write Complexity | Special Handling |
|---|---|---|---|
| `words` | HIGH (search, $in, graph, full scan) | MEDIUM (upsert, canonical migration) | `refresh_refs_for_new_key` needs RPC |
| `users` | LOW (point reads) | LOW ($set only; no $inc after XP RPC) | — |
| `user_sessions` | LOW (point read) | LOW (insert, delete) | TTL cleanup needed |
| `profiles` | LOW (point read) | MEDIUM ($set, need atomic streak) | — |
| `user_word_progress` | MEDIUM ($in, filter, sort) | HIGH (upsert full doc) | Must include all NOT NULL cols in upsert |
| `saved_words` | LOW | LOW (upsert + delete) | — |
| `study_sessions` | LOW | LOW (insert) | `source_mongo_id` stays NULL for new records |
| `analytics_events` | N/A (write-only) | LOW (insert) | `source_mongo_id` stays NULL |
| `ai_coach_content` | LOW (point read) | LOW (insert) | — |
| `ai_coach_usage` | LOW (count by date) | LOW (insert) | — |
| `tts_cache` | LOW (point read) | LOW (insert bytes) | BYTEA ↔ Python bytes must be tested |
| `topics` | LOW | LOW (seed insert) | — |
| `exams` | LOW | LOW (seed insert) | — |
| `articles` | LOW | LOW (seed insert) | Partial projection (body excluded) |
| `subscriptions` | N/A | LOW (upsert) | — |

---

## END OF AUDIT REPORT

**Status:** ✅ AUDIT COMPLETE  
**Next step:** Awaiting user approval to proceed to Stage 3 implementation.  
**DO NOT implement any code until explicitly approved.**
