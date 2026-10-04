"""Manual end-to-end smoke test for the AI platform + admin API (localhost)."""
import asyncio, json, time
import httpx

BASE = "http://localhost:8001/api"
ADMIN_EMAIL = "qa_admin@vocabist.com"
ADMIN_PW = "adminpass123"


async def main():
    async with httpx.AsyncClient(timeout=180) as c:
        # register or login admin
        r = await c.post(f"{BASE}/auth/register", json={"email": ADMIN_EMAIL, "password": ADMIN_PW, "name": "Admin"})
        if r.status_code != 200:
            r = await c.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
        print("auth", r.status_code)
        tok = r.json().get("token") or r.json().get("session_token")
        H = {"Authorization": f"Bearer {tok}"}

        me = await c.get(f"{BASE}/admin/me", headers=H)
        print("admin/me", me.status_code, me.json())

        dash = await c.get(f"{BASE}/admin/dashboard", headers=H)
        print("dashboard", dash.status_code)
        print(json.dumps(dash.json().get("vocabulary"), indent=1))

        models = await c.get(f"{BASE}/admin/ai/models", headers=H)
        print("models count", len(models.json().get("models", [])))

        routing = await c.get(f"{BASE}/admin/ai/routing", headers=H)
        print("routing tasks", len(routing.json().get("routing", [])))

        # ping nemotron lightning (real availability)
        ping = await c.post(f"{BASE}/admin/ai/models/nemotron-lightning/ping", headers=H)
        print("ping lightning", ping.status_code, ping.json())

        # create a small generation job
        job = await c.post(f"{BASE}/admin/ai/jobs", headers=H,
                           json={"count": 3, "cefr": "B2", "topic": "Academic", "enrichment_level": "standard"})
        print("create job", job.status_code, job.json().get("id"), job.json().get("status"))
        jid = job.json().get("id")

        # poll
        for _ in range(30):
            await asyncio.sleep(4)
            jr = await c.get(f"{BASE}/admin/ai/jobs/{jid}", headers=H)
            j = jr.json()
            print("job", j.get("status"), "valid", j.get("valid_count"), "gen", j.get("generated_count"), j.get("log", [])[-1:])
            if j.get("status") in ("COMPLETED", "PARTIAL", "FAILED", "CANCELLED"):
                break

        rev = await c.get(f"{BASE}/admin/vocabulary/review?limit=5", headers=H)
        print("review queue total", rev.json().get("total"))
        words = rev.json().get("words", [])
        if words:
            wid = words[0]["id"]
            print("sample review word", wid, words[0].get("headword"), words[0].get("cefr"))
            # translate test
            tr = await c.post(f"{BASE}/admin/ai/translate", headers=H,
                              json={"text": "knowledge", "target_language": "Spanish"})
            print("translate", tr.status_code, tr.json().get("translation"), tr.json().get("model_key"))
            # embed test
            em = await c.post(f"{BASE}/admin/ai/embed", headers=H, json={"text": "hello", "input_type": "query"})
            print("embed dims", em.json().get("dimensions"), em.json().get("model_key"))
            # publish it
            pub = await c.post(f"{BASE}/admin/vocabulary/{wid}/publish", headers=H)
            print("publish", pub.status_code, pub.json().get("status") if pub.status_code == 200 else pub.json())

        usage = await c.get(f"{BASE}/admin/ai/usage", headers=H)
        u = usage.json()
        print("usage", u.get("requests_total"), "success_rate", u.get("success_rate"), "by_model", u.get("by_model"))


asyncio.run(main())
