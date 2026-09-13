"""Seed blog posts so the community page isn't empty on first visit."""
import json


SEED_POSTS = [
    {"title": "How MEDIC saved my production database in 14 seconds",
     "body": "It was 2 AM. Our checkout service started throwing 5xx errors. Nobody was on call.\n\nBut MEDIC was. It detected the anomaly in 14 seconds, correlated it with a config change we'd pushed 20 minutes earlier, reproduced the fault in an isolated sandbox, and opened a pull request with the fix.\n\nThe crazy part? I woke up, reviewed the PR with my morning coffee, clicked approve, and the service was healthy.\n\nThis is what 'AI SRE' actually means — not a chatbot that tells you what might be wrong, but an agent that does the work of the on-call engineer while you sleep.",
     "tags": ["medic", "sre", "automation"], "author": "blog:umangvijay35@gmail.com"},
    {"title": "Why your AI agents need a security gateway (not just guardrails)",
     "body": "I tested every open-source LLM app I could find. Most had no security layer at all.\n\nThen I built SENTINEL — a reverse proxy that sits between your app and any LLM. It catches prompt injections, jailbreaks, and PII leakage (Aadhaar numbers, phone numbers, emails) in real time, scanning token-by-token as the response streams.\n\nThe key insight: scanning the final response is too late. By then, the PII is already in your logs, your context window, and possibly your user's browser. SENTINEL scans chunks as they arrive and redacts mid-stream.\n\nIf you're building with LLMs, put a gateway in front of them. Your compliance team will thank you.",
     "tags": ["sentinel", "security", "llm"], "author": "blog:umangvijay35@gmail.com"},
    {"title": "The star of return: why durable agents matter more than smart agents",
     "body": "Every AI framework promises 'production-ready agents.' But what happens when the process crashes mid-task? When the server restarts during a deploy? When an approval takes three days?\n\nMost frameworks lose state. The agent starts over from scratch. You lose the work, the cost, the time.\n\nPunarvasu — Sanskrit for 'return of the light' — is built on a different principle: runs are event-sourced. Every step is persisted. Kill the process, restart it, and the run resumes exactly where it stopped. Pause for human approval and come back three days later — the run is still there, waiting.\n\nThis isn't a nice-to-have. It's the difference between a demo and a system you trust.",
     "tags": ["durability", "architecture", "philosophy"], "author": "blog:umangvijay35@gmail.com"},
    {"title": "OPERATOR: teaching an AI to use a computer like a person",
     "body": "Most web automation tools use CSS selectors or XPath. OPERATOR doesn't. It looks at the screen like a human does — takes a screenshot, overlays numbered markers on every clickable element, and asks a vision model 'what should I click next?'\n\nWhen the click doesn't produce the expected change, it replans. When it encounters a form it's never seen, it fills it by reading the labels. And every successful sequence is remembered — so the next time it visits the same page, it replays the learned trajectory instantly.\n\nThis is the future of automation: not brittle selectors, but agents that see, act, verify and learn.",
     "tags": ["operator", "vision", "automation"], "author": "blog:umangvijay35@gmail.com"},
]

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # repo backend/ on sys.path

import asyncio


async def main():
    from app.config import settings  # canonical db url — no second database file, ever
    if not os.environ.get("ASTRAEA_DATABASE_URL"):
        os.environ["ASTRAEA_DATABASE_URL"] = settings.db_url
    from app.db import init_db, SessionLocal
    from app.core.models import Tenant, User
    from app.shared.security import hash_password
    from app.loom import service as loom

    await init_db()
    async with SessionLocal() as db:
        # create founder account
        founder = (await db.execute(
            __import__("sqlalchemy").select(User).where(User.email == "founder@astraea.local")
        )).scalar_one_or_none()
        if founder is None:
            tenant = Tenant(name="Astraea HQ")
            db.add(tenant)
            await db.flush()
            db.add(User(tenant_id=tenant.id, email="founder@astraea.local",
                        password_hash=hash_password("FounderAstraea2026!"),
                        full_name="Umang Vijay", role="superadmin"))
            await db.commit()
            await db.refresh(founder) if False else None
            founder = (await db.execute(
                __import__("sqlalchemy").select(User).where(User.email == "founder@astraea.local")
            )).scalar_one()

        for post in SEED_POSTS:
            from sqlalchemy import select as sq
            existing = (await db.execute(
                sq(__import__("app.loom.models", fromlist=["LoomItem"]).LoomItem)
                .where(__import__("app.loom.models", fromlist=["LoomItem"]).LoomItem.title == post["title"])
            )).scalar_one_or_none()
            if existing is None:
                await loom.write_item(
                    db, founder.tenant_id, origin_module=post["author"],
                    origin_run_id=None, kind="blog",
                    title=post["title"], summary=post["body"][:200],
                    payload={"body": post["body"], "tags": post["tags"]},
                )
                print(f"  blog created: {post['title'][:50]}")
    print("blog seeding complete")


asyncio.run(main())
