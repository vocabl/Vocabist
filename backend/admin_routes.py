"""Internal Admin API — server-side protected control center for the AI platform.

Every endpoint requires an admin session. Admin identity is a server-side email
allowlist (ADMIN_EMAILS) layered on the EXISTING custom auth system — no new
auth system, no client-only checks, no hard-coded password.

Mounted by server.py via build_admin_router(repo, get_current_user).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ai import registry, router as ai_router, usage as ai_usage, state_store, jobs
from ai.gateway import gateway
from ai.schemas import (
    RoutingUpdateBody, ModelToggleBody, GenerateBody, RegenerateFieldBody,
    TranslateBody, RejectBody, ALL_TASKS, ModelStatus,
)
from ai.tasks import translation as t_translation
from ai.tasks import embeddings as t_embeddings
from ai.tasks import multimodal as t_multimodal
from ai.tasks import semantic_search as t_semantic
from ai import embedding_jobs
from ai import insights as ai_insights
from ai.errors import AIError
from content_validation import validate_word
from content_ingest import bulk_ingest
from vocab_schema import normalize_headword


def _admin_emails() -> set:
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_admin_router(repo, get_current_user):
    router = APIRouter(prefix="/api/admin")

    async def get_current_admin(request: Request) -> dict:
        user = await get_current_user(request)
        email = (user.get("email") or "").lower()
        if email not in _admin_emails():
            raise HTTPException(status_code=403, detail="Admin access required")
        return user

    # ------------------------------------------------------------------ #
    # whoami — lets the client decide whether to show the Admin entry
    # ------------------------------------------------------------------ #
    @router.get("/me")
    async def admin_me(user: dict = Depends(get_current_user)):
        email = (user.get("email") or "").lower()
        return {"is_admin": email in _admin_emails(), "email": user.get("email")}

    # ------------------------------------------------------------------ #
    # DASHBOARD
    # ------------------------------------------------------------------ #
    @router.get("/dashboard")
    async def dashboard(admin: dict = Depends(get_current_admin)):
        vocab = {
            "total": await repo.count_collection("words"),
            "published": await repo.count_words_by_status("PUBLISHED"),
            "review": await repo.count_words_by_status("REVIEW"),
            "draft": await repo.count_words_by_status("DRAFT"),
            "archived": await repo.count_words_by_status("ARCHIVED"),
            "ai_generated": await repo.count_words_by_provenance("AI_GENERATED"),
        }
        cfg = await state_store.load_config()
        cfg_models = cfg.get("models", {})
        providers = [registry.merge_state(s, cfg_models) for s in registry.all_models()]
        usage_agg = await ai_usage.aggregate()
        all_jobs = await state_store.list_jobs(limit=100)
        job_summary = {
            "total": len(all_jobs),
            "running": sum(1 for j in all_jobs if j.get("status") == "RUNNING"),
            "completed": sum(1 for j in all_jobs if j.get("status") == "COMPLETED"),
            "partial": sum(1 for j in all_jobs if j.get("status") == "PARTIAL"),
            "failed": sum(1 for j in all_jobs if j.get("status") == "FAILED"),
        }
        return {
            "vocabulary": vocab,
            "ai": usage_agg,
            "providers": providers,
            "jobs": job_summary,
            "nvidia_configured": registry.provider_has_key("nvidia"),
            "emergent_configured": registry.provider_has_key("emergent"),
        }

    # ------------------------------------------------------------------ #
    # AI — PROVIDERS / MODELS
    # ------------------------------------------------------------------ #
    @router.get("/ai/providers")
    async def ai_providers(admin: dict = Depends(get_current_admin)):
        cfg = await state_store.load_config()
        cfg_models = cfg.get("models", {})
        models = [registry.merge_state(s, cfg_models) for s in registry.all_models()]
        by_provider: Dict[str, Dict[str, Any]] = {}
        for m in models:
            p = m["provider"]
            bucket = by_provider.setdefault(p, {
                "provider": p,
                "configured": registry.provider_has_key(p),
                "models": [],
            })
            bucket["models"].append(m)
        return {"providers": list(by_provider.values())}

    @router.get("/ai/models")
    async def ai_models(admin: dict = Depends(get_current_admin)):
        cfg = await state_store.load_config()
        cfg_models = cfg.get("models", {})
        return {"models": [registry.merge_state(s, cfg_models) for s in registry.all_models()]}

    @router.post("/ai/models/{key}/toggle")
    async def toggle_model(key: str, body: ModelToggleBody, admin: dict = Depends(get_current_admin)):
        if not registry.get_model(key):
            raise HTTPException(status_code=404, detail="Unknown model")
        await state_store.update_model_state(key, {"enabled": body.enabled})
        cfg = await state_store.load_config()
        return registry.merge_state(registry.get_model(key), cfg.get("models", {}))

    @router.post("/ai/models/{key}/ping")
    async def ping_model(key: str, admin: dict = Depends(get_current_admin)):
        if not registry.get_model(key):
            raise HTTPException(status_code=404, detail="Unknown model")
        return await gateway.ping(key)

    # ------------------------------------------------------------------ #
    # AI — ROUTING
    # ------------------------------------------------------------------ #
    @router.get("/ai/routing")
    async def get_routing(admin: dict = Depends(get_current_admin)):
        cfg = await state_store.load_config()
        return {"routing": ai_router.routing_view(cfg), "tasks": ALL_TASKS}

    @router.put("/ai/routing")
    async def put_routing(body: RoutingUpdateBody, admin: dict = Depends(get_current_admin)):
        if body.task not in ALL_TASKS:
            raise HTTPException(status_code=400, detail="Unknown task")
        invalid = [k for k in body.chain if not ai_router.capability_valid(body.task, k)]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Models {invalid} lack the required capability for {body.task}",
            )
        await state_store.set_routing(body.task, body.chain, body.enabled)
        cfg = await state_store.load_config()
        return {"routing": ai_router.routing_view(cfg)}

    # ------------------------------------------------------------------ #
    # AI — USAGE
    # ------------------------------------------------------------------ #
    @router.get("/ai/usage")
    async def ai_usage_view(admin: dict = Depends(get_current_admin)):
        return await ai_usage.aggregate()

    # ------------------------------------------------------------------ #
    # AI — JOBS
    # ------------------------------------------------------------------ #
    @router.get("/ai/jobs")
    async def list_jobs(admin: dict = Depends(get_current_admin)):
        return {"jobs": await state_store.list_jobs(limit=100)}

    @router.post("/ai/jobs")
    async def create_job(body: GenerateBody, admin: dict = Depends(get_current_admin)):
        if body.cefr and body.cefr not in {"A1", "A2", "B1", "B2", "C1", "C2"}:
            raise HTTPException(status_code=400, detail="Invalid CEFR")
        if body.exam:
            slugs = await repo.get_exam_slugs()
            if body.exam not in slugs:
                raise HTTPException(status_code=400, detail=f"Unknown exam '{body.exam}'")
        if body.model and not ai_router.capability_valid("vocabulary_generation", body.model):
            raise HTTPException(status_code=400, detail="Chosen model cannot generate vocabulary")
        job = await jobs.create_generation_job(repo, body.model_dump(), admin["user_id"])
        return job

    @router.get("/ai/jobs/{job_id}")
    async def get_job(job_id: str, admin: dict = Depends(get_current_admin)):
        job = await state_store.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @router.post("/ai/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str, admin: dict = Depends(get_current_admin)):
        job = await jobs.cancel_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    # ------------------------------------------------------------------ #
    # VOCABULARY — REVIEW QUEUE
    # ------------------------------------------------------------------ #
    @router.get("/vocabulary/review")
    async def review_queue(
        search: Optional[str] = None, offset: int = 0, limit: int = 50,
        admin: dict = Depends(get_current_admin),
    ):
        total, words = await repo.list_words_by_status(
            "REVIEW", provenance=None, search=search, offset=offset, limit=limit,
        )
        return {"total": total, "words": words}

    @router.get("/vocabulary/all")
    async def all_words(
        status: str = "PUBLISHED", search: Optional[str] = None,
        offset: int = 0, limit: int = 50, admin: dict = Depends(get_current_admin),
    ):
        total, words = await repo.list_words_by_status(
            status, provenance=None, search=search, offset=offset, limit=limit,
        )
        return {"total": total, "words": words}

    @router.get("/vocabulary/{word_id}")
    async def get_word(word_id: str, admin: dict = Depends(get_current_admin)):
        w = await repo.get_word(word_id)
        if not w:
            raise HTTPException(status_code=404, detail="Word not found")
        validation = await _validate(word_id, w)
        return {"word": w, "validation": validation}

    async def _validate(word_id: str, w: Dict[str, Any]) -> Dict[str, Any]:
        minimal = await repo.load_all_words_minimal()
        id_by_key: Dict[str, str] = {}
        for x in minimal:
            k = normalize_headword(x.get("headword", ""))
            if k and k not in id_by_key:
                id_by_key[k] = x["id"]
        exam_slugs = await repo.get_exam_slugs()
        res = validate_word(
            w, id_by_key=id_by_key, known_word_ids=set(id_by_key.values()),
            known_exam_slugs=exam_slugs, existing_id=word_id,
        )
        return res.to_dict()

    @router.post("/vocabulary/{word_id}/regenerate")
    async def regenerate_field(
        word_id: str, body: RegenerateFieldBody, admin: dict = Depends(get_current_admin),
    ):
        from ai.tasks import enrichment
        w = await repo.get_word(word_id)
        if not w:
            raise HTTPException(status_code=404, detail="Word not found")
        try:
            out = await enrichment.regenerate_field(
                w, body.field, prefer_model=body.model, admin_id=admin["user_id"],
            )
        except AIError as e:
            raise HTTPException(status_code=502, detail=f"Regeneration failed: {e.code}")
        # persist the regenerated field, preserving provenance/lifecycle
        await repo.update_word(word_id, {out["json_key"]: out["value"], "updated_at": _now_iso()})
        updated = await repo.get_word(word_id)
        return {"field": out["field"], "value": out["value"], "model": out["model_key"],
                "fallback_used": out["fallback_used"], "word": updated}

    async def _set_status(word_id: str, status: str) -> Dict[str, Any]:
        w = await repo.get_word(word_id)
        if not w:
            raise HTTPException(status_code=404, detail="Word not found")
        await repo.update_word(word_id, {"status": status, "updated_at": _now_iso()})
        return await repo.get_word(word_id)

    @router.post("/vocabulary/{word_id}/approve")
    async def approve(word_id: str, admin: dict = Depends(get_current_admin)):
        w = await repo.get_word(word_id)
        if not w:
            raise HTTPException(status_code=404, detail="Word not found")
        validation = await _validate(word_id, w)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail={"message": "Validation failed", "validation": validation})
        updated = await _set_status(word_id, "PUBLISHED")
        return {"word": updated, "status": "PUBLISHED"}

    @router.post("/vocabulary/{word_id}/publish")
    async def publish(word_id: str, admin: dict = Depends(get_current_admin)):
        w = await repo.get_word(word_id)
        if not w:
            raise HTTPException(status_code=404, detail="Word not found")
        validation = await _validate(word_id, w)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail={"message": "Validation failed", "validation": validation})
        updated = await _set_status(word_id, "PUBLISHED")
        return {"word": updated, "status": "PUBLISHED"}

    @router.post("/vocabulary/{word_id}/reject")
    async def reject(word_id: str, body: RejectBody, admin: dict = Depends(get_current_admin)):
        updated = await _set_status(word_id, "ARCHIVED")
        return {"word": updated, "status": "ARCHIVED", "reason": body.reason}

    @router.post("/vocabulary/{word_id}/archive")
    async def archive(word_id: str, admin: dict = Depends(get_current_admin)):
        updated = await _set_status(word_id, "ARCHIVED")
        return {"word": updated, "status": "ARCHIVED"}

    # ------------------------------------------------------------------ #
    # AI SERVICES — translation / embedding / multimodal (admin-controlled)
    # ------------------------------------------------------------------ #
    @router.post("/ai/translate")
    async def translate(body: TranslateBody, admin: dict = Depends(get_current_admin)):
        try:
            return await t_translation.translate(
                body.text, source_language=body.source_language,
                target_language=body.target_language, prefer_model=body.model,
                admin_id=admin["user_id"],
            )
        except AIError as e:
            raise HTTPException(status_code=502, detail=f"Translation failed: {e.code}")

    @router.post("/ai/embed")
    async def embed(payload: Dict[str, Any], admin: dict = Depends(get_current_admin)):
        text = str(payload.get("text", "")).strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        input_type = payload.get("input_type", "query")
        try:
            if input_type == "passage":
                return await t_embeddings.embed_passages([text], admin_id=admin["user_id"])
            return await t_embeddings.embed_query(text, admin_id=admin["user_id"])
        except AIError as e:
            raise HTTPException(status_code=502, detail=f"Embedding failed: {e.code}")

    @router.post("/ai/multimodal/extract")
    async def multimodal_extract(payload: Dict[str, Any], admin: dict = Depends(get_current_admin)):
        image = str(payload.get("image", "")).strip()  # data URL
        if not image.startswith("data:image"):
            raise HTTPException(status_code=400, detail="image must be a data URL")
        try:
            out = await t_multimodal.extract_from_image(
                image, max_words=int(payload.get("max_words", 15)),
                instruction=str(payload.get("instruction", "")),
                admin_id=admin["user_id"],
            )
        except AIError as e:
            raise HTTPException(status_code=502, detail=f"Extraction failed: {e.code}")
        entries = out.get("entries", [])
        ingest = await bulk_ingest(repo, entries, provenance="AI_GENERATED") if entries else {"created": 0}
        return {"extracted": len(entries), "ingested": ingest, "model": out.get("model_key")}

    # ------------------------------------------------------------------ #
    # EMBEDDINGS — Admin management
    # ------------------------------------------------------------------ #
    @router.get("/embeddings/status")
    async def embedding_status(admin: dict = Depends(get_current_admin)):
        stats = await repo.get_embedding_stats()
        return stats

    @router.post("/embeddings/jobs")
    async def create_embedding_job(
        payload: Dict[str, Any] = {},
        admin: dict = Depends(get_current_admin),
    ):
        mode = payload.get("mode", "missing")
        if mode not in ("missing", "stale", "all", "selected"):
            raise HTTPException(status_code=400, detail="Invalid mode")
        word_ids = payload.get("word_ids")
        job = await embedding_jobs.create_embedding_job(
            repo,
            mode=mode,
            word_ids=word_ids,
            admin_id=admin["user_id"],
        )
        return job

    @router.get("/embeddings/jobs")
    async def list_embedding_jobs(admin: dict = Depends(get_current_admin)):
        jobs_list = await repo.list_embedding_jobs(limit=50)
        return {"jobs": jobs_list}

    # ------------------------------------------------------------------ #
    # MODEL INSIGHTS — enhanced analytics
    # ------------------------------------------------------------------ #
    @router.get("/ai/insights")
    async def get_insights(
        model: Optional[str] = None,
        task: Optional[str] = None,
        provider: Optional[str] = None,
        days: int = 30,
        admin: dict = Depends(get_current_admin),
    ):
        return await ai_insights.model_insights(
            model_filter=model,
            task_filter=task,
            provider_filter=provider,
            days=days,
        )

    # ------------------------------------------------------------------ #
    # BULK VOCABULARY — enhanced generation with full config
    # ------------------------------------------------------------------ #
    @router.post("/vocabulary/bulk-generate")
    async def bulk_generate(payload: Dict[str, Any], admin: dict = Depends(get_current_admin)):
        count = int(payload.get("count", 10))
        if count > 500:
            raise HTTPException(status_code=400, detail="Maximum 500 words per job")
        if count > 100:
            # Require confirmation for large jobs
            confirmed = payload.get("confirmed", False)
            if not confirmed:
                return {
                    "requires_confirmation": True,
                    "message": f"You are about to generate {count} vocabulary items. This will consume significant AI resources.",
                    "count": count,
                }
        body = GenerateBody(
            count=count,
            cefr=payload.get("cefr"),
            topic=payload.get("topic"),
            part_of_speech=payload.get("part_of_speech"),
            exam=payload.get("exam"),
            vocabulary_type=payload.get("vocabulary_type"),
            model=payload.get("model"),
            enrichment_level=payload.get("enrichment_level", "standard"),
        )
        if body.cefr and body.cefr not in {"A1", "A2", "B1", "B2", "C1", "C2"}:
            raise HTTPException(status_code=400, detail="Invalid CEFR")
        if body.exam:
            slugs = await repo.get_exam_slugs()
            if body.exam not in slugs:
                raise HTTPException(status_code=400, detail=f"Unknown exam '{body.exam}'")
        job = await jobs.create_generation_job(repo, body.model_dump(), admin["user_id"])
        return job

    # ------------------------------------------------------------------ #
    # BULK APPROVE / REJECT
    # ------------------------------------------------------------------ #
    @router.post("/vocabulary/bulk-approve")
    async def bulk_approve(payload: Dict[str, Any], admin: dict = Depends(get_current_admin)):
        word_ids = payload.get("word_ids", [])
        if not word_ids:
            raise HTTPException(status_code=400, detail="No word IDs provided")
        if len(word_ids) > 100:
            confirmed = payload.get("confirmed", False)
            if not confirmed:
                return {
                    "requires_confirmation": True,
                    "message": f"You are about to publish {len(word_ids)} words.",
                    "count": len(word_ids),
                }
        results = {"published": 0, "failed": 0, "errors": []}
        for wid in word_ids:
            try:
                w = await repo.get_word(wid)
                if not w:
                    results["failed"] += 1
                    results["errors"].append({"id": wid, "error": "Not found"})
                    continue
                validation = await _validate(wid, w)
                if not validation["valid"]:
                    results["failed"] += 1
                    results["errors"].append({"id": wid, "error": "Validation failed"})
                    continue
                await repo.update_word(wid, {"status": "PUBLISHED", "updated_at": _now_iso()})
                results["published"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({"id": wid, "error": str(e)})
        return results

    @router.post("/vocabulary/bulk-reject")
    async def bulk_reject(payload: Dict[str, Any], admin: dict = Depends(get_current_admin)):
        word_ids = payload.get("word_ids", [])
        reason = payload.get("reason", "Bulk rejected by admin")
        if not word_ids:
            raise HTTPException(status_code=400, detail="No word IDs provided")
        results = {"rejected": 0, "failed": 0}
        for wid in word_ids:
            try:
                await repo.update_word(wid, {"status": "ARCHIVED", "updated_at": _now_iso()})
                results["rejected"] += 1
            except Exception:
                results["failed"] += 1
        return results

    return router
