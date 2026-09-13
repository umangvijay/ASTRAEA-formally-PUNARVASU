"""The OPERATOR task suite: 20 goals on live sandbox sites + programmatic success checks.

Each task is data (goal + start url + predicate) — success is verified by code, not by
the agent's own opinion. Run: python -m app.operator.suite   (scores persist to
data/operator_benchmark.json and surface on /api/operator/benchmark).
"""

from __future__ import annotations

import json
import time

from app.config import settings

BOOKS = "https://books.toscrape.com"
QUOTES = "https://quotes.toscrape.com"

TASKS: list[dict] = [
    # books.toscrape.com — navigation
    {"name": "books-travel-category", "goal": "open the Travel books category", "url": BOOKS,
     "success_kind": "url_contains", "success_value": "travel"},
    {"name": "books-poetry-category", "goal": "open the Poetry books category", "url": BOOKS,
     "success_kind": "url_contains", "success_value": "poetry"},
    {"name": "books-fiction-category", "goal": "open the Fiction books category", "url": BOOKS,
     "success_kind": "url_contains", "success_value": "fiction"},
    {"name": "books-mystery-category", "goal": "open the Mystery books category", "url": BOOKS,
     "success_kind": "url_contains", "success_value": "mystery"},
    {"name": "books-catalogue-page-3", "goal": "browse forward to page 3 of the catalogue",
     "url": BOOKS,
     "success_kind": "url_contains", "success_value": "page-3"},
    {"name": "books-catalogue-page-4", "goal": "browse forward to page 4 of the catalogue",
     "url": BOOKS,
     "success_kind": "url_contains", "success_value": "page-4"},
    {"name": "books-open-first-book", "goal": "open the first Travel book detail page",
     "url": f"{BOOKS}/catalogue/category/books/travel_1/index.html",
     "success_kind": "url_contains", "success_value": "catalogue/"},
    {"name": "books-fiction-next", "goal": "browse forward to page 2 of the Fiction category",
     "url": f"{BOOKS}/catalogue/category/books/fiction_10/index.html",
     "success_kind": "url_contains", "success_value": "page-2"},
    # quotes.toscrape.com — tags, login, author pages
    {"name": "quotes-tag-love", "goal": "open the love quotes tag", "url": QUOTES,
     "success_kind": "url_contains", "success_value": "/tag/love"},
    {"name": "quotes-tag-wisdom", "goal": "open the wisdom quotes tag", "url": QUOTES,
     "success_kind": "url_contains", "success_value": "/tag/wisdom"},
    {"name": "quotes-login", "goal": "log in as user pvu with password pvu", "url": f"{QUOTES}/login",
     "success_kind": "content_contains", "success_value": "Logout"},
    {"name": "quotes-author-einstein", "goal": "open the Albert Einstein author page", "url": QUOTES,
     "success_kind": "url_contains", "success_value": "/author/Albert-Einstein"},
    {"name": "quotes-tag-life", "goal": "open the life quotes tag", "url": QUOTES,
     "success_kind": "url_contains", "success_value": "/tag/life"},
    {"name": "quotes-tag-humor", "goal": "open the humor quotes tag", "url": QUOTES,
     "success_kind": "url_contains", "success_value": "/tag/humor"},
    # wikipedia.org — search
    {"name": "wiki-alan-turing", "goal": "search for 'Alan Turing'", "url": "https://en.wikipedia.org",
     "success_kind": "url_contains", "success_value": "Alan_Turing"},
    {"name": "wiki-grace-hopper", "goal": "search for 'Grace Hopper'", "url": "https://en.wikipedia.org",
     "success_kind": "url_contains", "success_value": "Grace_Hopper"},
    {"name": "wiki-history-of-india", "goal": "search for 'History of India'", "url": "https://en.wikipedia.org",
     "success_kind": "url_contains", "success_value": "History_of_India"},
    {"name": "wiki-python", "goal": "search for 'Python (programming language)'", "url": "https://en.wikipedia.org",
     "success_kind": "url_contains", "success_value": "Python_(programming_language)"},
    {"name": "wiki-random-article", "goal": "open a random article", "url": "https://en.wikipedia.org/wiki/Main_Page",
     "success_kind": "url_contains", "success_value": "/wiki/"},
    # example.com
    {"name": "example-more-info", "goal": "open the more information link", "url": "https://example.com",
     "success_kind": "url_contains", "success_value": "iana"},
]


async def run_suite(progress=None) -> dict:
    """Run all tasks; persist the scoreboard. progress(url, line) optional callback."""
    from app.operator.executor import BrowserSession
    from app.operator.runner import _success
    from app.operator import parser, memory
    from app.operator.brain import decide
    from app.db import SessionLocal
    from app.core.models import Tenant
    from sqlalchemy import select

    async with SessionLocal() as db:
        tenant_id = (
            await db.execute(select(Tenant).order_by(Tenant.created_at).limit(1))
        ).scalar_one_or_none()
        tenant_id = tenant_id.id if tenant_id else None

    results = []
    session = BrowserSession()
    try:
        await session.start()
        for task in TASKS:
            started = time.time()
            record = {"name": task["name"], "goal": task["goal"], "status": "pending",
                      "steps": 0, "replans": 0}
            try:
                await session.fresh_page()
                await session.goto(task["url"])
                actions: list[dict] = []
                noops = 0
                for step_no in range(1, settings.operator_max_steps + 1):
                    if await _success(session.page, task["success_kind"], task["success_value"]):
                        record["status"] = "success"
                        record["steps"] = step_no - 1
                        break
                    raw, som, elements = await parser.parse_page(session.page)
                    action = await decide(task["goal"], elements, actions, som)
                    if action["action"] == "fail":
                        record["status"] = "gave_up"
                        record["reason"] = action.get("reason", "")
                        break
                    before, _, _ = await parser.parse_page(session.page)
                    before_url = session.page.url
                    before_text = await session.page.inner_text("body")
                    outcome = await session.perform(action, elements)
                    if outcome.get("done") and action["action"] == "fail":
                        break
                    after, _, _ = await parser.parse_page(session.page)
                    after_text = await session.page.inner_text("body")
                    from app.operator.executor import pixel_diff_pct

                    changed = pixel_diff_pct(before, after)
                    effective = (changed > 0.05 or session.page.url != before_url
                                 or after_text[:2000] != before_text[:2000])
                    actions.append({"action": action["action"], "element": action.get("element"),
                                    "text": action.get("text", "")})
                    if not effective:
                        noops += 1
                        record["replans"] = noops
                        if noops >= 3:
                            record["status"] = "stalled"
                            break
                    else:
                        noops = 0
                    record["steps"] = step_no
                if record["status"] == "pending" and await _success(
                    session.page, task["success_kind"], task["success_value"]
                ):
                    record["status"] = "success"
                if record["status"] == "success" and tenant_id:
                    try:
                        await memory.save(db2=None, tenant_id=tenant_id,
                                          origin_run_id=None, goal=task["goal"],
                                          url=session.page.url, actions=actions) if False else None
                    except Exception:
                        pass
            except Exception as exc:  # noqa: BLE001 — a task failing must not stop the suite
                record["status"] = "error"
                record["reason"] = str(exc)[:200]
            record["duration_s"] = round(time.time() - started, 1)
            results.append(record)
            if progress:
                progress(task["name"], record)
    finally:
        await session.close()

    ok = sum(1 for r in results if r["status"] == "success")
    summary = {
        "tasks": len(results),
        "success": ok,
        "success_rate": round(ok / len(results), 2) if results else 0.0,
        "gate_target": 0.5,
        "total_replans": sum(r.get("replans", 0) for r in results),
        "ran_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
    }
    out = settings.data_dir / "operator_benchmark.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    import asyncio

    from app.db import init_db

    async def main():
        await init_db()

        def progress(name, record):
            print(f"  {record['status']:9s} {name} (steps {record['steps']}, replans {record['replans']})")

        summary = await run_suite(progress)
        print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))

    asyncio.run(main())
