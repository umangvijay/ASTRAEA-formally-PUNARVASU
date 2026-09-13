"""FORGE tests: verifiable eval harness, promotion ONLY on measured improvement,
failure mining from real run_events, git-committed champion memory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings
from app.forge import eval as forge_eval
from app.forge.models import ForgeChampion, ForgeEvalRun
from app.db import SessionLocal


@pytest.fixture(autouse=True)
def _fake_llm(monkeypatch):
    """A provider double whose behaviour is driven by the PROMPT TEXT: the 'v2' variant
    produces correct SQL; the base template produces broken SQL. Deterministic scores."""
    from app.sentinel import llm as sentinel_llm

    from app.model_forge.data_gen import generate_tasks

    gold_by_question = {t.question: t.gold_sql for t in generate_tasks(200, seed=23)}

    async def fake_complete(db, tenant_id, messages, **kwargs):
        prompt = messages[-1]["content"]
        question = next((l for l in prompt.splitlines() if l.startswith("Question:")), "")
        question = question.removeprefix("Question: ").strip()
        if "v2-enhanced" in prompt and question in gold_by_question:
            return {"content": gold_by_question[question], "provider": "test-double", "usage": {}}
        return {"content": "SELECT * FROM nonexistent_table_xyz", "provider": "test-double", "usage": {}}

    monkeypatch.setattr(sentinel_llm, "complete", fake_complete)


async def test_data_generator_tasks_are_verifiable():
    from app.model_forge.data_gen import build_db, generate_tasks

    tasks = generate_tasks(20, seed=3)
    conn = build_db()
    for t in tasks[:5]:
        rows = conn.execute(t.gold_sql).fetchall()
        assert rows is not None  # every gold SQL must execute
        assert t.expected_rows == [list(map(str, r)) for r in rows]


async def test_promotion_only_on_measured_improvement(app, auth_headers):
    """Bootstrap: first eval (score 0) becomes champion. A better candidate promotes;
    a worse one is rejected. Every promotion is a git commit."""
    # 1. bootstrap the champion with a 0-score variant
    async with SessionLocal() as db:
        run0 = await forge_eval.run_eval(db, variant_kind="prompt-variant",
                                         payload={"prompt_template": "base template"}, variant_name="bootstrap")
        await forge_eval.promote_if_better(db, eval_run=run0, candidate=None,
                                           kind="prompt-variant", payload={"prompt_template": "base template"})
    assert run0.score == 0.0

    # 2. a better candidate (v2) must promote
    async with SessionLocal() as db:
        run1 = await forge_eval.run_eval(db, variant_kind="prompt-variant",
                                         payload={"prompt_template": "v2-enhanced\nQuestion: {question}"},
                                         variant_name="v2")
        cand = await forge_eval.propose_candidate(db, source="manual", kind="prompt-variant",
                                                  reason="test v2",
                                                  payload={"prompt_template": "v2-enhanced\nQuestion: {question}"})
        verdict = await forge_eval.promote_if_better(db, eval_run=run1, candidate=cand,
                                                     kind="prompt-variant",
                                                     payload={"prompt_template": "v2-enhanced\nQuestion: {question}"})
    assert verdict["promoted"] is True, verdict
    assert run1.promoted is True

    async with SessionLocal() as db:
        champ = (await db.execute(
            select(ForgeChampion).where(ForgeChampion.capability == "sql-writer")
        )).scalar_one()
        assert champ.prompt_template == "v2-enhanced\nQuestion: {question}"
        assert champ.score == run1.score

    # 3. a WORSE candidate must be rejected — never promoted
    async with SessionLocal() as db:
        run2 = await forge_eval.run_eval(db, variant_kind="prompt-variant",
                                         payload={"prompt_template": "worse"}, variant_name="worse-1")
        cand2 = await forge_eval.propose_candidate(db, source="manual", kind="prompt-variant",
                                                   reason="worse candidate",
                                                   payload={"prompt_template": "worse"})
        verdict2 = await forge_eval.promote_if_better(db, eval_run=run2, candidate=cand2,
                                                      kind="prompt-variant",
                                                      payload={"prompt_template": "worse"})
    assert verdict2["promoted"] is False
    assert cand2.status == "rejected"

    # 4. the champion memory is a real git repo with real commits
    repo = Path(settings.data_dir) / "forge" / "repo" / ".git"
    assert repo.exists(), "champion changes must be git-committed"
    champion_json = json.loads((repo.parent / "champion.json").read_text())
    assert champion_json["prompt_template"] == "v2-enhanced\nQuestion: {question}"


async def test_failure_mining_proposes_from_real_events(app, auth_headers):
    tenant_id = decode_tid(auth_headers)
    async with SessionLocal() as db:
        from app.core.models import Run, RunEvent

        run = Run(tenant_id=tenant_id, goal="g", workflow=[{"name": "s", "type": "tool"}],
                  origin_module="medic")
        db.add(run)
        await db.flush()
        for i in range(3):
            db.add(RunEvent(run_id=run.id, type="step_failed", node="shell",
                            payload={"tool": "shell", "error": "tool timeout after 10s"}))
        await db.commit()

    async with SessionLocal() as db:
        mining = await forge_eval.mine_failures(db)
    assert mining["clusters"] >= 1
    top = mining["proposals"][0]
    assert "timeout" in json.dumps(top["change"]).lower()


def decode_tid(auth_headers) -> str:
    from app.shared.security import decode_access_token

    return decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]
