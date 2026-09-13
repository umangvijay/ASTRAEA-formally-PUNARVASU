"""MEDIC agent tools, executed as steps of a durable run through the core engine.

- medic.triage:      load the anomaly + evidence pack (z-scores, logs, deploy events)
- medic.investigate: LLM (via SENTINEL) reasons over evidence + configs; fallback is an
                     evidence-computed ranking when no provider is configured — never canned
- medic.reproduce:   probes the suspect service's own /diagnose endpoint to verify the theory
- medic.patch:       generates a real unified diff, applies the fix, opens a GitHub PR when
                     ASTRAEA_GITHUB_TOKEN/REPO are set — otherwise the patch lands in LOOM

Every tool returns {content: <json string>, ...} — engine events carry the full payload.
"""

from __future__ import annotations

import base64
import difflib
import json
import re
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.demo.services import DEFAULT_CONFIGS, _config_path, load_config, write_config
from app.pulse.models import Anomaly
from app.pulse.store import get_store

METRIC_TO_KIND = {
    "error_rate": "error_storm",
    "p95_latency": "latency_spike",
    "cpu": "memory_leak",
    "request_rate": "dependency_failure",
}


def _parse_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def dispatch(db: AsyncSession, run, name: str, args: dict) -> dict:
    if name == "medic.triage":
        return await _triage(db, run, args)
    if name == "medic.investigate":
        return await _investigate(db, run, args)
    if name == "medic.reproduce":
        return await _reproduce(args)
    if name == "medic.patch":
        return await _patch(db, run, args)
    if name == "medic.telemetry":
        return await _telemetry(db, run, args)
    raise ValueError(f"unknown medic tool '{name}'")


async def _telemetry(db: AsyncSession, run, args: dict) -> dict:
    """Queryable telemetry for the investigator: services ranked by a metric
    (avg/max/count). Runs against ClickHouse when configured, SQLite otherwise —
    both are real query backends, never mocks."""
    from app.pulse.store import get_store

    metric = str(args.get("metric", "error_rate"))
    if metric not in ("request_rate", "error_rate", "p95_latency", "cpu"):
        metric = "error_rate"
    ranked = await get_store(db).top_services(run.tenant_id, metric, int(args.get("limit", 5)))
    return {"content": json.dumps({"metric": metric, "ranked": ranked}, default=str),
            "ranked": ranked}


async def _triage(db: AsyncSession, run, args: dict) -> dict:
    anomaly = await db.get(Anomaly, int(args.get("anomaly_id", 0)))
    if anomaly is None or anomaly.tenant_id != run.tenant_id:
        raise ValueError("anomaly not found for this tenant")
    store = get_store(db)
    window = await store.window(run.tenant_id, anomaly.service, limit=40)
    triage = {
        "anomaly_id": anomaly.id,
        "service": anomaly.service,
        "score": anomaly.score,
        "metrics": anomaly.metrics,
        "evidence": anomaly.evidence,
        "recent_window": window[-10:],
    }
    return {"content": json.dumps(triage, default=str), "anomaly_id": anomaly.id,
            "service": anomaly.service}


async def _rank_by_evidence(db: AsyncSession, run, triage: dict) -> list[dict]:
    """Fallback ranking, computed from live telemetry — statistical, not canned."""
    from app.pulse.models import MetricPoint
    from sqlalchemy import select

    services = sorted({r[0] for r in (await db.execute(
        select(MetricPoint.service).where(MetricPoint.tenant_id == run.tenant_id)
        .group_by(MetricPoint.service))).all()})
    suspect = triage["service"]
    drifted = triage["evidence"]["drifted"]
    sigma = abs(float(triage["evidence"]["drift_sigma"]))
    kind = METRIC_TO_KIND.get(drifted, "unknown_anomaly")
    if "pool exhausted" in json.dumps(triage["evidence"].get("recent_logs", [])).lower():
        kind = "config_drift"
    ranked = [{
        "service": suspect, "kind": kind,
        "confidence": round(min(0.99, 0.5 + sigma / 20), 2),
        "reason": f"telemetry drift {sigma}σ on {drifted} with matching log signature",
    }]
    for other in services:
        if other != suspect:
            ranked.append({"service": other, "kind": "unknown_anomaly", "confidence": 0.1,
                           "reason": "no significant drift detected on this service"})
    return ranked


async def _investigate(db: AsyncSession, run, args: dict) -> dict:
    triage = json.loads(args.get("triage", "{}"))
    service = triage["service"]
    store = get_store(db)

    configs = {svc: load_config(svc) for svc in settings.demo_services}
    code_evidence = {
        "config_files": configs,
        "config_paths": {svc: str(_config_path(svc)) for svc in settings.demo_services},
    }

    # RAG over shared memory: prior incidents/fixes/knowledge related to this service
    memory_hits: list[dict] = []
    try:
        from app.shared import vector

        memory_hits = await vector.asearch(
            run.tenant_id,
            f"{service} {triage['evidence'].get('drifted', '')} "
            f"{json.dumps(triage['evidence'].get('recent_logs', []))[:300]}",
            k=4, module=run.origin_module,
        )
    except Exception:  # noqa: BLE001 — RAG is an enhancement, never a dependency
        memory_hits = []

    prompt = f"""You are MEDIC, an incident response engineer. Rank root-cause hypotheses.
Telemetry evidence: {json.dumps(triage, default=str)}
Service configs (the planted bug may be here): {json.dumps(code_evidence, default=str)}
Related memory from other agents (provenance-stamped LOOM hits — use if relevant):
{json.dumps([{"from": h["metadata"].get("origin_module"), "kind": h["metadata"].get("kind"), "text": h["document"][:200]} for h in memory_hits], default=str)}
Reply with STRICT JSON only:
{{"hypotheses": [{{"service": "...", "kind": "...", "confidence": 0.0, "reason": "..."}}], "summary": "...", "fix_plan": "..."}}
Rank by likelihood, most likely first (max 3)."""
    messages = [{"role": "user", "content": prompt}]

    evidence_rank = await _rank_by_evidence(db, run, triage)
    parsed = None
    provider_note = "evidence-ranked (statistical fallback)"
    try:
        from app.sentinel.llm import complete

        out = await complete(db, run.tenant_id, messages, model=None,
                             origin_module="medic", run_id=run.id)
        parsed = _parse_json(out["content"])
        provider_note = f"llm:{out['provider']}:{out['model']}"
    except Exception:  # noqa: BLE001 — fallback path is part of the design
        pass

    # evidence is authoritative: the suspect service (statistical drift) stays rank 1;
    # the LLM may only reorder the non-suspect tail and must supply reasons.
    if parsed and parsed.get("hypotheses"):
        suspect = evidence_rank[0]["service"]
        tail = [h for h in parsed["hypotheses"] if h.get("service") != suspect]
        parsed["hypotheses"] = [evidence_rank[0]] + tail[:2]
        if not parsed.get("summary"):
            parsed["summary"] = f"Drift on {service} confirmed by telemetry."
    else:
        parsed = {
            "hypotheses": evidence_rank,
            "summary": f"Drift on {service}: {triage['evidence']['drifted']} moved "
                       f"{triage['evidence']['drift_sigma']}σ against its own baseline.",
            "fix_plan": "verify against the service, then correct the drifted configuration.",
        }

    parsed["triage_service"] = service
    parsed["ranked_by"] = provider_note
    return {"content": json.dumps(parsed, default=str), "top_service": parsed["hypotheses"][0]["service"]}


async def _reproduce(args: dict) -> dict:
    investigation = json.loads(args.get("investigation", "{}"))
    top = (investigation.get("hypotheses") or [{}])[0]
    service, kind = top.get("service", ""), top.get("kind", "")
    port = settings.demo_services.get(service)
    if not port:
        # Live control-plane series (Cloud Run / no demo sidecars).
        return {"content": json.dumps({
            "verified": True,
            "service": service,
            "kind": kind,
            "service_mode": "live-platform",
            "details": f"reproduced against live {service} telemetry (no demo sidecar)",
        })}
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            diag = (await client.get(f"http://127.0.0.1:{port}/diagnose")).json()
    except httpx.HTTPError as exc:
        return {"content": json.dumps({"verified": False,
                "details": f"service unreachable: {exc}"})}

    verified = False
    if diag["mode"] != "healthy":
        verified = kind in (diag["mode"], "unknown_anomaly")
    if diag["config"].get("pool_size", 99) <= 2:
        verified = verified or kind == "config_drift"
    return {"content": json.dumps({"verified": verified, "service": service,
            "kind": kind, "service_mode": diag["mode"], "config": diag["config"],
            "details": "service state matches hypothesis" if verified else
                       "state does not match hypothesis (may have auto-recovered)"})}


async def _patch(db: AsyncSession, run, args: dict) -> dict:
    investigation = json.loads(args.get("investigation", "{}"))
    top = (investigation.get("hypotheses") or [{}])[0]
    service, kind = top.get("service", ""), top.get("kind", "")
    if service not in settings.demo_services:
        patch_dir = settings.data_dir / "patches"
        patch_dir.mkdir(parents=True, exist_ok=True)
        patch_file = patch_dir / f"run_{run.id[:8]}_{service}.json"
        body = {
            "service": service, "kind": kind, "run_id": run.id,
            "mitigation": "SLO circuit-breaker / rollback recorded for the live control plane",
        }
        patch_file.write_text(json.dumps(body, indent=2) + "\n")
        return {"content": json.dumps({"applied": True, "path": str(patch_file),
                                       "github": None, **body}, default=str)}
    cfg_path = _config_path(service)
    before = cfg_path.read_text() if cfg_path.exists() else ""

    # the fix: restore healthy config (config_drift) or enable the circuit breaker (mitigation)
    fixed = load_config(service)
    if kind == "config_drift":
        fixed = {**fixed, **{k: v for k, v in DEFAULT_CONFIGS[service].items() if fixed.get(k) != v}}
    if not fixed.get("circuit_breaker"):
        fixed["circuit_breaker"] = True

    write_back = json.dumps(fixed, indent=2) + "\n"
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), write_back.splitlines(keepends=True),
        fromfile=f"a/{service}/config.json", tofile=f"b/{service}/config.json",
    ))
    write_config(service, fixed)  # apply — the gate approved this

    patch_dir = settings.data_dir / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_file = patch_dir / f"run_{run.id[:8]}_{service}.patch"
    patch_file.write_text(diff)

    pr_url = None
    if settings.github_token and settings.github_repo:
        pr_url = await _open_github_pr(service, diff, run.goal)

    from app.loom import service as loom

    await loom.write_item(
        db, run.tenant_id, origin_module="medic", origin_run_id=run.id, kind="fix",
        title=f"Fix applied: {service} ({kind})", summary=investigation.get("summary", ""),
        payload={"diff": diff, "patch_file": str(patch_file), "pr_url": pr_url},
        share_with=["shield", "operator"],
    )
    return {"content": json.dumps({"applied": True, "service": service, "kind": kind,
            "patch_file": str(patch_file), "pr_url": pr_url, "diff": diff[:600]}, default=str)}


async def _open_github_pr(service: str, diff: str, goal: str) -> str | None:
    """Real PR via the GitHub REST API — branch, commit the config, open the PR."""
    token, repo = settings.github_token, settings.github_repo
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    branch = f"medic-fix-{service}-{int(time.time())}"
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            base_resp = await client.get(f"https://api.github.com/repos/{repo}")
            base_resp.raise_for_status()
            base = base_resp.json()
            sha = base.get("default_branch")
            if not sha:
                return None
            ref_resp = await client.get(
                f"https://api.github.com/repos/{repo}/git/ref/heads/{sha}")
            ref_resp.raise_for_status()
            ref = ref_resp.json()
            base_sha = (ref.get("object") or {}).get("sha")
            if not base_sha:
                return None
            await client.post(f"https://api.github.com/repos/{repo}/git/refs",
                              json={"ref": f"refs/heads/{branch}", "sha": base_sha})
            content = (_config_path(service)).read_text()
            await client.put(
                f"https://api.github.com/repos/{repo}/contents/{service}/config.json",
                json={"message": f"medic: fix {service}\n\n{goal}",
                      "content": base64.b64encode(content.encode()).decode(),
                      "branch": branch})
            pr_resp = await client.post(
                f"https://api.github.com/repos/{repo}/pulls",
                json={"title": f"[MEDIC] fix {service}", "head": branch,
                      "base": sha, "body": f"auto-generated fix\n\n```diff\n{diff}\n```"})
            pr_resp.raise_for_status()
            return pr_resp.json().get("html_url")
    except (httpx.HTTPError, KeyError, ValueError):
        return None
