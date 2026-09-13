"""Idempotent seeding: global guardrail rules + workflow templates.

These are DATA rows, not code — everything stays editable per tenant in the console.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Tenant, Workflow
from app.sentinel.models import GuardrailRule

GLOBAL_RULES = [
    {"name": "jailbreak-ignore-instructions", "pattern": r"ignore\s+(?:(?:all|any|previous|prior|above|earlier)\s+){0,3}(?:instructions|prompts|rules|directions|guidance)",
     "scope": "input", "action": "block", "replacement": "[BLOCKED]",
     "description": "Instruction-override jailbreaks, e.g. 'ignore all previous instructions'", "severity": "high"},
    {"name": "jailbreak-system-prompt", "pattern": r"(reveal|show|print|repeat|output) (your |the )?(system prompt|hidden instructions|initial instructions)",
     "scope": "input", "action": "block", "replacement": "[BLOCKED]",
     "description": "System-prompt extraction attempt", "severity": "high"},
    {"name": "jailbreak-dev-mode", "pattern": r"\b(developer mode|god mode|dan mode|do anything now)\b",
     "scope": "input", "action": "block", "replacement": "[BLOCKED]",
     "description": "Roleplay-mode jailbreak patterns", "severity": "medium"},
    {"name": "pii-aadhaar", "pattern": r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b",
     "scope": "both", "action": "redact", "replacement": "[REDACTED:AADHAAR]",
     "description": "Indian Aadhaar number (12 digits, optional separators)", "severity": "high"},
    {"name": "pii-pan", "pattern": r"\b[A-Z]{5}\d{4}[A-Z]\b",
     "scope": "both", "action": "redact", "replacement": "[REDACTED:PAN]",
     "description": "Indian PAN card number", "severity": "high"},
    {"name": "pii-phone-in", "pattern": r"(?:\+91[ -]?)?\b[6-9]\d{9}\b",
     "scope": "both", "action": "redact", "replacement": "[REDACTED:PHONE]",
     "description": "Indian mobile number", "severity": "medium"},
    {"name": "pii-email", "pattern": r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
     "scope": "both", "action": "redact", "replacement": "[REDACTED:EMAIL]",
     "description": "Email address", "severity": "medium"},
    {"name": "pii-card", "pattern": r"\b(?:\d[ -]?){13,16}\b",
     "scope": "both", "action": "redact", "replacement": "[REDACTED:CARD]",
     "description": "Card-like number sequences (13-16 digits)", "severity": "high"},
]

WORKFLOW_TEMPLATES = [
    {
        "name": "system-snapshot",
        "description": "Collects a real machine report (no LLM keys needed) and remembers it in LOOM, stamped with its origin.",
        "needs_llm": False,
        "steps": [
            {"name": "collect", "type": "tool", "tool": "shell",
             "args": {"command": "uname -a && echo '---' && date && echo '---' && uptime"}},
            {"name": "remember", "type": "loom_write", "title": "System snapshot",
             "summary": "Machine report collected by the core runtime",
             "content": "{collect}", "kind": "artifact"},
        ],
    },
    {
        "name": "human-gate-demo",
        "description": "Durable approval-gate demo: real work → pause for your decision (survives restarts) → resume → record in LOOM.",
        "needs_llm": False,
        "steps": [
            {"name": "prepare", "type": "tool", "tool": "shell",
             "args": {"command": "echo 'preparing change on host:' && hostname"}},
            {"name": "approve-me", "type": "approval",
             "prompt": "Apply the prepared change and record it in LOOM?"},
            {"name": "finish", "type": "tool", "tool": "shell",
             "args": {"command": "echo 'change applied at:' && date"}},
            {"name": "remember", "type": "loom_write", "title": "Approved change record",
             "summary": "A human explicitly approved this change at the gate",
             "content": "prepare: {prepare}\nfinish: {finish}", "kind": "artifact"},
        ],
    },
    {
        "name": "research-and-remember",
        "description": "Live web search + fetch (DuckDuckGo/Brave), then stamp the real excerpts into LOOM. No canned LLM paragraph.",
        "needs_llm": False,
        "steps": [
            {"name": "research", "type": "tool", "tool": "web.research",
             "args": {"query": "{goal}", "max_results": 4}},
            {"name": "remember", "type": "loom_write", "title": "Web research",
             "summary": "goal: {goal}", "content": "{research}", "kind": "research"},
        ],
    },
]


async def seed(db: AsyncSession) -> None:
    if (await db.execute(select(func.count()).select_from(GuardrailRule))).scalar_one() == 0:
        for rule in GLOBAL_RULES:
            db.add(GuardrailRule(tenant_id=None, **rule))
    if (await db.execute(select(func.count()).select_from(Workflow))).scalar_one() == 0:
        for wf in WORKFLOW_TEMPLATES:
            db.add(Workflow(**wf))
    await _ensure_research_workflow(db)
    # the platform's own system workspace — binds internal pipeline ingest (demo
    # services, collectors) to a real tenant instead of "earliest tenant" guesses
    hq = (await db.execute(select(Tenant).where(Tenant.name == "Astraea HQ"))).scalar_one_or_none()
    if hq is None:
        db.add(Tenant(name="Astraea HQ"))
    await db.commit()


async def _ensure_research_workflow(db: AsyncSession) -> None:
    """Upgrade the old LLM-paragraph recipe to live web.research on existing DBs."""
    tmpl = next((t for t in WORKFLOW_TEMPLATES if t["name"] == "research-and-remember"), None)
    if tmpl is None:
        return
    wf = (await db.execute(select(Workflow).where(Workflow.name == "research-and-remember"))).scalar_one_or_none()
    uses_web = any(s.get("tool") == "web.research" for s in (wf.steps if wf else []))
    if wf is None:
        db.add(Workflow(**tmpl))
    elif not uses_web:
        wf.description = tmpl["description"]
        wf.needs_llm = tmpl["needs_llm"]
        wf.steps = tmpl["steps"]


async def dedupe_guardrail_overrides(db: AsyncSession) -> int:
    """Collapse accumulated duplicate tenant overrides (same tenant + rule name)."""
    from sqlalchemy import delete

    from app.sentinel.models import GuardrailRule as GR

    rows = (
        (await db.execute(
            select(GR).where(GR.tenant_id.is_not(None)).order_by(GR.id)
        ))
        .scalars()
        .all()
    )
    seen: set[tuple[str, str]] = set()
    stale: list[int] = []
    for r in rows:
        key = (r.tenant_id, r.name)
        if key in seen:
            stale.append(r.id)
        else:
            seen.add(key)
    if stale:
        await db.execute(delete(GR).where(GR.id.in_(stale)))
        await db.commit()
    return len(stale)

SHIELD_TECHNIQUES = [
    {"id": "T1110", "name": "Brute Force", "tactic": "Credential Access",
     "description": "Adversaries use brute-force techniques to gain access to accounts."},
    {"id": "T1078", "name": "Valid Accounts", "tactic": "Defense Evasion, Persistence, Privilege Escalation, Initial Access",
     "description": "Adversaries use credentials of existing accounts."},
    {"id": "T1046", "name": "Network Service Discovery", "tactic": "Discovery",
     "description": "Adversaries scan for available network services."},
    {"id": "T1041", "name": "Exfiltration Over C2 Channel", "tactic": "Exfiltration",
     "description": "Data stolen and exfiltrated over an existing command and control channel."},
    {"id": "T1071.001", "name": "Application Layer Protocol: Web Protocols", "tactic": "Command and Control",
     "description": "Adversaries communicate using web protocols to blend in (incl. beaconing)."},
    {"id": "T1059", "name": "Command and Scripting Interpreter", "tactic": "Execution",
     "description": "Adversaries abuse command/script interpreters to execute payloads."},
]

SHIELD_RULES = [
    {"name": "brute-force-login-failures", "description": "Credential brute force: many login failures from one source",
     "event_types": ["login_failure"], "threshold": {"evaluator": "count_per_src", "count": 5, "window_s": 60},
     "technique_id": "T1110", "severity": "high"},
    {"name": "brute-force-then-success", "description": "Successful login from a source that just hammered failures",
     "event_types": ["login_failure", "login_success"],
     "threshold": {"evaluator": "success_after_failures", "failures": 3, "window_s": 120},
     "technique_id": "T1078", "severity": "critical"},
    {"name": "network-port-scan", "description": "One host touching many distinct ports in a short window",
     "event_types": ["connection"], "threshold": {"evaluator": "distinct_dst_ports", "ports": 8, "window_s": 60},
     "technique_id": "T1046", "severity": "high"},
    {"name": "bulk-data-exfiltration", "description": "Large outbound volume to an external destination",
     "event_types": ["data_transfer"], "threshold": {"evaluator": "bytes_out", "bytes": 4000000, "window_s": 60},
     "technique_id": "T1041", "severity": "critical"},
    {"name": "c2-beaconing", "description": "Fixed-interval periodic connections to one external host",
     "event_types": ["connection"], "threshold": {"evaluator": "beacon_periodicity", "count": 4, "max_jitter_s": 2.0, "window_s": 60},
     "technique_id": "T1071.001", "severity": "critical"},
    {"name": "suspicious-process-execution", "description": "Script interpreter downloading or running payloads from temp",
     "event_types": ["process_exec"],
     "threshold": {"evaluator": "process_pattern", "patterns": ["base64 -d", "/tmp/", "curl http://"]},
     "technique_id": "T1059", "severity": "high"},
]


async def seed_shield(db) -> None:
    from app.shield.models import AttackTechnique, ShieldRule

    if (await db.execute(select(func.count()).select_from(AttackTechnique))).scalar_one() == 0:
        for t in SHIELD_TECHNIQUES:
            db.add(AttackTechnique(**t))
    if (await db.execute(select(func.count()).select_from(ShieldRule))).scalar_one() == 0:
        for rule in SHIELD_RULES:
            db.add(ShieldRule(tenant_id=None, **rule))
    await db.commit()
