"""Module registry — the single source of truth for products, profiles and phases.

Used by the API (/api/modules) and mirrored by the console. Every product module
works SOLO (own compose profile) and combined (FUSION). Spec §2.
"""

MODULES: list[dict] = [
    {
        "codename": "medic",
        "name": "MEDIC",
        "title": "AI SRE — the on-call engineer",
        "profile": "sre",
        "phase": 2,
        "blurb": "Watches live telemetry, detects anomalies, correlates with deploys, reproduces the fault in a sandbox and opens the fix PR for your approval.",
        "benchmark": "MTTD / MTTR on injected faults",
    },
    {
        "codename": "operator",
        "name": "OPERATOR",
        "title": "Vision computer-use agent",
        "profile": "operator",
        "phase": 3,
        "blurb": "Operates screens where no API exists — vision-guided clicking and typing with self-correction, verified by screenshot diff, learning trajectories as it goes.",
        "benchmark": "Success rate on a 20-task web suite",
    },
    {
        "codename": "shield",
        "name": "SHIELD",
        "title": "AI SOC analyst",
        "profile": "soc",
        "phase": 4,
        "blurb": "Defensive cyber agent: streams security events, correlates attacks into narratives, maps MITRE ATT&CK, graphs the intrusion and drafts containment for approval.",
        "benchmark": "Detection rate / false-positive rate",
    },
    {
        "codename": "vaani",
        "name": "VAANI",
        "title": "Voice AI employee",
        "profile": "voice",
        "phase": 5,
        "blurb": "Full-duplex voice agent that answers calls and completes the work — books, follows up, hands over to humans. Sub-1.5s end-to-end, barge-in included.",
        "benchmark": "p95 latency + task completion",
    },
    {
        "codename": "forge",
        "name": "FORGE",
        "title": "Self-evolving engine",
        "profile": "forge",
        "phase": 6,
        "blurb": "Turns agent failures into new skills: proposes tools and prompt patches, validates them in a sandbox, promotes only measured wins.",
        "benchmark": "Week-over-week eval score",
    },
    {
        "codename": "model_forge",
        "name": "MODEL-FORGE",
        "title": "Our own model",
        "profile": "core",
        "phase": 6,
        "blurb": "A domain-expert model post-trained by us (SFT + GRPO on verifiable rewards) and served behind SENTINEL — our proprietary edge.",
        "benchmark": "Held-out SQL test pass rate vs base model",
    },
]

CORE_SERVICES: list[dict] = [
    {
        "codename": "sentinel",
        "name": "SENTINEL",
        "phase": 1,
        "blurb": "LLM security firewall — every model call in the platform passes through it. Prompt-injection, jailbreak and Indic-PII detection, streaming output scanning, per-tenant metering.",
    },
    {
        "codename": "loom",
        "name": "LOOM",
        "phase": 1,
        "blurb": "The shared context fabric: your data and everything the agents learn, stored once, provenance-stamped, available to every module you switch on — never re-entered.",
    },
    {
        "codename": "pulse",
        "name": "PULSE",
        "phase": 2,
        "blurb": "Real-time telemetry bus: logs, metrics, traces and security events flowing into one queryable stream that feeds MEDIC and SHIELD alike.",
    },
]


def module_status(codename: str, active_profile: str) -> str:
    """Phase 0: shells are ready but modules land in later phases."""
    for m in MODULES:
        if m["codename"] == codename:
            if m["phase"] == 0:
                return "up"
            return f"phase-{m['phase']}"
    return "unknown"
