"""OPERATOR tests: local end-to-end tasks, self-correction, verifier, trajectory reuse.

Everything runs against in-browser local content (page.set_content) — no network needed.
"""

from __future__ import annotations

import json

import pytest

from app.operator import memory
from app.operator.executor import ensure_playwright_browsers, pixel_diff_pct
from app.operator.runner import run_task

_CHROMIUM = ensure_playwright_browsers()
needs_chromium = pytest.mark.skipif(
    not _CHROMIUM, reason="Playwright Chromium is not installed (playwright install chromium)"
)

CLICK_PAGE = """
<h1>Pvu Portal</h1>
<a id="go" href="#welcome">Enter the welcome section</a>
<script>
document.getElementById('go').addEventListener('click', () => {
  const d = document.createElement('div');
  d.textContent = 'WELCOME REACHED';
  document.body.appendChild(d);
});
</script>
"""

SELF_CORRECT_PAGE = """
<h1>Wizard</h1>
<button id="step1">Start the wizard</button>
<script>
document.getElementById('step1').addEventListener('click', () => {
  document.body.innerHTML = '<h1>Wizard</h1><button id="confirm">Confirm the wizard now</button>';
  document.getElementById('confirm').addEventListener('click', () => {
    const d = document.createElement('div');
    d.textContent = 'WIZARD CONFIRMED';
    document.body.appendChild(d);
  });
});
</script>
"""


async def test_pixel_diff_detects_change():
    a = b"\x89PNG fake"  # not real — use generated images instead
    from PIL import Image
    import io

    def png(color):
        buf = io.BytesIO()
        Image.new("RGB", (50, 50), color).save(buf, format="PNG")
        return buf.getvalue()

    assert pixel_diff_pct(png("white"), png("white")) == 0.0
    assert pixel_diff_pct(png((0, 0, 0)), png((255, 255, 255))) > 90.0


def test_heuristic_brain_picks_matching_link():
    from app.operator.brain import heuristic

    elements = [
        {"id": 0, "tag": "a", "role": "link", "text": "Home", "placeholder": ""},
        {"id": 1, "tag": "a", "role": "link", "text": "Travel books category", "placeholder": ""},
    ]
    action = heuristic("open the Travel books category", elements, [])
    assert action["action"] == "click" and action["element"] == 1


@needs_chromium
async def test_end_to_end_local_task_success(app, auth_headers):
    tenant_headers = auth_headers
    token = tenant_headers["Authorization"].removeprefix("Bearer ")
    from app.shared.security import decode_access_token

    tenant_id = decode_access_token(token)["tid"]
    run_id = await _make_run(tenant_id, html=CLICK_PAGE,
                             goal="open the welcome section",
                             success_kind="content_contains", success_value="WELCOME REACHED")
    await engine_execute(run_id)
    run = await _run(run_id)
    assert run.status == "completed", run.error
    result = json.loads(run.result["outputs"]["operate"])
    assert result["success"] is True


@needs_chromium
async def test_trajectory_saved_then_reused(app, auth_headers):
    from app.shared.security import decode_access_token

    tenant_id = decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]

    run_id = await _make_run(tenant_id, html=CLICK_PAGE, goal="open the welcome section",
                             success_kind="content_contains", success_value="WELCOME REACHED")
    await engine_execute(run_id)
    run = await _run(run_id)
    assert run.status == "completed", run.error
    assert run.result, run.error
    result = json.loads(run.result["outputs"]["operate"])
    assert result["success"] and result.get("trajectory_id"), "trajectory not saved on success"

    async with SessionLocalCompat() as db:
        retrieved = await memory.retrieve(db, tenant_id, "open the welcome section")
    assert retrieved and retrieved["actions"], "trajectory not retrievable"

    # a repeat of the same goal retrieves the trajectory before acting
    run_id2 = await _make_run(tenant_id, html=CLICK_PAGE, goal="open the welcome section",
                              success_kind="content_contains", success_value="WELCOME REACHED")
    await engine_execute(run_id2)
    run2 = await _run(run_id2)
    assert run2.status == "completed", run2.error
    assert run2.result, run2.error
    result2 = json.loads(run2.result["outputs"]["operate"])
    assert result2["success"]
    assert result2.get("reused_trajectory"), "repeat task did not reuse the trajectory"


@needs_chromium
async def test_self_correction_on_mutating_page(app, auth_headers):
    """The page changes under the agent mid-task; verifier+replan must recover."""
    from app.shared.security import decode_access_token

    tenant_id = decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]
    run_id = await _make_run(tenant_id, html=SELF_CORRECT_PAGE,
                             goal="confirm the wizard",
                             success_kind="content_contains", success_value="WIZARD CONFIRMED")
    await engine_execute(run_id)
    run = await _run(run_id)
    assert run.status == "completed", run.error
    assert run.result, run.error
    result = json.loads(run.result["outputs"]["operate"])
    assert result["success"] is True
    assert result["steps"] >= 2  # needed more than one round to finish


# ── helpers ────────────────────────────────────────────────────────
def SessionLocalCompat():
    from app.db import SessionLocal

    return SessionLocal()


async def _make_run(tenant_id: str, html: str, goal: str, success_kind: str, success_value: str) -> str:
    from app.core import engine
    from app.core.models import Run

    steps = engine.validate_workflow([
        {"name": "operate", "type": "tool", "tool": "operator.run_task",
         "args": {"goal": goal, "html": html, "success_kind": success_kind,
                  "success_value": success_value}},
    ])
    async with SessionLocalCompat() as db:
        run = Run(tenant_id=tenant_id, goal=goal, workflow=steps, origin_module="operator")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run.id


async def engine_execute(run_id: str) -> None:
    from app.core import engine

    await engine.execute(run_id)


async def _run(run_id: str):
    from app.core.models import Run
    from app.db import SessionLocal

    async with SessionLocal() as db:
        return await db.get(Run, run_id)
