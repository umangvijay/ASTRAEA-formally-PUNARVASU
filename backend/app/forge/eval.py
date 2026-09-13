"""FORGE: mine real failures → propose candidates → evaluate on the verifiable suite →
promote only on measured improvement → commit the champion to the agent's own git repo.

The eval capability Phase 6 ships is `sql-writer`: tasks generated from the demo schema,
reward = the SQL executes and returns the gold rows. The generator behind a variant is
pluggable: the current champion prompt, a candidate prompt, or the MODEL-FORGE weights.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.models import RunEvent
from app.forge.models import ForgeCandidate, ForgeChampion, ForgeEvalRun
from app.model_forge.data_gen import build_db, generate_tasks, rows_match

CAPABILITY = "sql-writer"
PROMPT_DATA_DIR = Path(settings.data_dir) / "forge"
SQL_TASKS = None  # lazy


def _tasks(n: int):
    global SQL_TASKS
    if SQL_TASKS is None:
        SQL_TASKS = generate_tasks(n + 40, seed=23)
    return SQL_TASKS[:n]


DEFAULT_CHAMPION_PROMPT = (
    "You write a single SQLite query. Reply with the SQL only, no prose.\n"
    "Schema: {schema}\nQuestion: {question}"
)


async def _current_champion(db: AsyncSession) -> ForgeChampion:
    champ = (
        await db.execute(select(ForgeChampion).where(ForgeChampion.capability == CAPABILITY))
    ).scalar_one_or_none()
    if champ is None:
        champ = ForgeChampion(
            capability=CAPABILITY, kind="prompt", score=0.0,
            prompt_template=DEFAULT_CHAMPION_PROMPT,
        )
        db.add(champ)
        await db.commit()
        await db.refresh(champ)
    elif not champ.prompt_template:
        # heal rows damaged by the old promote path (template wiped to NULL)
        champ.prompt_template = DEFAULT_CHAMPION_PROMPT
        await db.commit()
        await db.refresh(champ)
    return champ


async def mine_failures(db: AsyncSession, tenant_id: str | None = None, limit: int = 200) -> dict:
    """Group real step_failed events by module+tool and propose a candidate per cluster.
    Tenant-scoped: a tenant's failures never leak into another tenant's proposals."""
    from app.core.models import Run as _Run

    q = (
        select(RunEvent)
        .join(_Run, RunEvent.run_id == _Run.id)
        .where(RunEvent.type.in_(["step_failed", "run_failed"]))
    )
    if tenant_id is not None:
        q = q.where(_Run.tenant_id == tenant_id)
    events = (
        (
            await db.execute(q.order_by(desc(RunEvent.id)).limit(limit))
        )
        .scalars()
        .all()
    )
    clusters: Counter = Counter()
    samples: dict[str, str] = {}
    for e in events:
        tool = (e.payload or {}).get("tool") or e.node or "unknown"
        key = f"{e.type}:{tool}"
        clusters[key] += 1
        samples.setdefault(key, (e.payload or {}).get("error", "")[:160])
    proposals = []
    for key, count in clusters.most_common(5):
        err = samples[key].lower()
        if "timeout" in err or "timed out" in err:
            change = {"suggestion": "increase tool timeout + add retry with backoff"}
        elif "not on screen" in err or "not found" in err:
            change = {"suggestion": "re-parse before acting; prefer trajectory replay on stale state"}
        elif "no element plausibly advances" in err:
            change = {"suggestion": "broaden element matching; add pagination fallback ordering"}
        elif "provider" in err:
            change = {"suggestion": "provider chain exhausted — check keys/model availability"}
        else:
            change = {"suggestion": f"inspect recurring {key} failures ({count} occurrences)"}
        proposals.append({
            "cluster": key, "occurrences": count, "sample_error": samples[key], "change": change,
        })
    return {"clusters": len(clusters), "proposals": proposals}


async def propose_candidate(db: AsyncSession, *, source: str, kind: str, reason: str,
                            payload: dict, module: str = "core",
                            tenant_id: str | None = None) -> ForgeCandidate:
    cand = ForgeCandidate(source=source, kind=kind, reason=reason, payload=payload,
                          module=module, tenant_id=tenant_id)
    db.add(cand)
    await db.commit()
    await db.refresh(cand)
    return cand


from app.model_forge.data_gen import SCHEMA_SQL as SCHEMA_SQL_STR


def _rows(conn: sqlite3.Connection, sql: str):
    return [list(map(str, r)) for r in conn.execute(sql).fetchall()]


async def run_eval(db: AsyncSession, *, variant_kind: str, payload: dict,
                   variant_name: str, task_count: int | None = None,
                   tenant_id: str | None = None) -> ForgeEvalRun:
    """Evaluate a variant on the verifiable SQL suite; record a ForgeEvalRun row.
    LLM usage is metered to `tenant_id` (the caller) — never a phantom tenant."""
    n = task_count or settings.forge_eval_size
    tasks = _tasks(n)
    champion = await _current_champion(db)

    if variant_kind == "model":
        passed, details = await _eval_sql(_model_generator_static(), tasks)
    else:
        template = payload.get("prompt_template") or champion.prompt_template or ""
        meter_tenant = tenant_id or "system"

        async def gen(question: str) -> str:
            from app.sentinel.llm import complete

            filled = template.replace("{schema}", SCHEMA_SQL_STR).replace("{question}", question)
            out = await complete(db, meter_tenant, [{"role": "user", "content": filled}],
                                 model=payload.get("model"))
            return out["content"].strip()

        passed, details = await _eval_sql(gen, tasks)

    score = round(passed / max(1, len(tasks)), 3)
    run = ForgeEvalRun(capability=CAPABILITY, variant=variant_name, passed=passed,
                       total=len(tasks), score=score, details={"tasks": details[:20]},
                       tenant_id=tenant_id)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


def _model_generator_static():
    from app.model_forge.serving import available as model_available

    assert model_available(), "model-forge weights not provisioned"

    async def gen(question: str) -> str:
        from app.model_forge.serving import generate

        return generate(
            "You write a single SQLite query. Reply with the SQL only, no prose.\n"
            f"Schema: {SCHEMA_SQL_STR}\nQuestion: {question}")

    return gen


async def _eval_sql(gen, tasks) -> tuple[int, list[dict]]:
    conn = build_db()
    passed, details = 0, []
    for t in tasks:
        ok = False
        sql = ""
        try:
            sql = _strip_sql(await gen(t.question))
            ok = rows_match(_rows(conn, sql), t.expected_rows)
        except Exception:  # noqa: BLE001 — bad SQL is a failed task
            ok = False
        passed += ok
        details.append({"question": t.question[:60], "passed": ok, "sql": sql[:80]})
    return passed, details


def _strip_sql(text: str) -> str:
    return (text or "").strip().removeprefix("```sql").removeprefix("```").removesuffix("```").strip()


async def promote_if_better(db: AsyncSession, *, eval_run: ForgeEvalRun,
                            candidate: ForgeCandidate | None, kind: str, payload: dict) -> dict:
    """Promotion is ONLY on measured improvement over the active champion."""
    champion = await _current_champion(db)
    if eval_run.score <= champion.score and champion.score > 0:
        eval_run.promoted = False
        if candidate:
            candidate.status = "rejected"
            candidate.score_before, candidate.score_after = champion.score, eval_run.score
        await db.commit()
        return {"promoted": False, "reason": f"score {eval_run.score} <= champion {champion.score}"}

    eval_run.promoted = True
    champion.kind = kind
    # only overwrite when the payload actually carries a value — a present-but-None
    # key must never wipe the champion's prompt or model path
    new_template = payload.get("prompt_template")
    if new_template:
        champion.prompt_template = new_template
    new_model_path = payload.get("model_path")
    if new_model_path:
        champion.model_path = new_model_path
    champion.score = eval_run.score
    if candidate:
        candidate.status = "promoted"
        candidate.score_before, candidate.score_after = champion.score, eval_run.score
    await db.commit()

    git_note = _git_commit_champion(champion, eval_run)
    return {"promoted": True, "score": eval_run.score, "git": git_note}


def _git_commit_champion(champion: ForgeChampion, eval_run: ForgeEvalRun) -> str:
    """The agent's own memory is a git repo: every champion change is a commit."""
    repo = PROMPT_DATA_DIR / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    state = {
        "capability": champion.capability, "kind": champion.kind, "score": champion.score,
        "prompt_template": champion.prompt_template, "model_path": champion.model_path,
        "eval_run": eval_run.id, "updated_at": eval_run.ran_at.isoformat(),
    }
    (repo / "champion.json").write_text(json.dumps(state, indent=2))

    def git(*args: str) -> str:
        out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
        return (out.stdout + out.stderr).strip()

    if not (repo / ".git").exists():
        git("init")
        git("config", "user.email", "forge@astraea.local")
        git("config", "user.name", "FORGE")
    git("add", "champion.json")
    msg = f"forge: promote {champion.capability} score={champion.score} (eval #{eval_run.id})"
    if git("commit", "-m", msg) or git("status", "--short"):
        return f"committed: {msg}"
    return "no change to commit"
