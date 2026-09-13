"""Central configuration. Everything env-driven — nothing hardcoded (Spec §4.1).

Env contract: canonical prefix is ASTRAEA_. A compat shim aliases legacy
PUNARVASU_* names (os env + .env file) so older .env files and launchers keep
working — but new code must only emit ASTRAEA_*.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]  # app/ → backend/ → repo root
_PREFIX = "ASTRAEA_"
_LEGACY_PREFIX = "PUNARVASU_"


def _alias_legacy_env() -> None:
    """Map PUNARVASU_X → ASTRAEA_X (real env wins; .env legacy keys aliased too)."""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(_LEGACY_PREFIX) and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(_PREFIX + key[len(_LEGACY_PREFIX):], val.strip())
    for key in [k for k in os.environ if k.startswith(_LEGACY_PREFIX)]:
        os.environ.setdefault(_PREFIX + key[len(_LEGACY_PREFIX):], os.environ[key])


_alias_legacy_env()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASTRAEA_", env_file=str(ROOT / ".env"), extra="ignore"
    )

    env: str = "dev"
    app_name: str = "Astraea"
    version: str = "0.3.0"
    phase: int = 7
    database_url: str = ""  # empty → resolved by db_url property
    jwt_secret: str = ""  # empty → ephemeral dev secret (warned by launcher)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    # localhost on ANY port is allowed by default (the launcher shifts ports on
    # collision); production locks this down via ASTRAEA_CORS_ORIGINS.
    cors_origins: str = ""
    # Regional Cloud Run hosts are {service}-{hash}.{region}.run.app — a single
    # DNS label before .run.app is not enough (that only matched the old URLs).
    cors_origin_regex: str = (
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?|"
        r"https://[a-z0-9.-]+\.run\.app|"
        r"https://[a-z0-9-]+\.web\.app"
    )
    active_profile: str = "full"  # full = every module heartbeat on; infra profiles only pick compose services
    mode: str = "sqlite"  # storage backend: sqlite | postgres
    backend_port: int = 8000

    # ── LLM providers (cloud + local fallback) ──
    gemini_api_key: str = ""
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    ollama_base_url: str = "http://127.0.0.1:11434/v1"  # local, no key, always available route
    # Vertex AI (GCloud) — ADC / access token / API key; same Gemini models, billed to the project
    vertex_project: str = ""
    vertex_location: str = "global"
    vertex_access_token: str = ""
    vertex_api_key: str = ""
    vertex_default_model: str = "gemini-3.8-flash"
    # Anthropic Claude (optional)
    anthropic_api_key: str = ""
    anthropic_default_model: str = "claude-sonnet-4-20250514"
    # Web research (OPERATOR) — DuckDuckGo is the zero-key default
    brave_api_key: str = ""
    # General-chat quality first; the SQL champion is only routed to by explicit
    # model hint ("pvu-sql"/"model_forge") — never as the default brain.
    llm_provider_order: str = "vertex,gemini,anthropic,groq,ollama,model_forge,mlx_local"
    gemini_default_model: str = "gemini-3.8-flash"
    groq_default_model: str = "llama-3.3-70b-versatile"
    ollama_default_model: str = "llama3.2"
    llm_timeout_seconds: int = 60

    # ── Durable run queue / workers (Milestone 2) ──
    run_lease_seconds: int = 30   # a claimed run must heartbeat within this window
    run_workers: int = 1          # in-process durable workers started at app boot
    run_worker_poll_seconds: float = 1.0

    # ── Tool sandbox (Milestone 3) ──
    # Untrusted shell/code tools run in an ephemeral Docker container (gVisor runtime
    # auto-used when present). Falls back — loudly — to host rlimits when Docker is absent.
    sandbox_enabled: bool = True
    sandbox_image: str = "alpine:3.20"
    sandbox_memory: str = "512m"
    sandbox_cpus: str = "1.0"
    sandbox_pids_limit: int = 128
    sandbox_network: str = "none"   # 'none' = no network egress from tool execution

    # ── Pulse (telemetry) + Medic ──
    clickhouse_url: str = ""  # e.g. http://127.0.0.1:8123 — sqlite telemetry store when empty
    detector_interval_seconds: int = 10
    anomaly_cooldown_seconds: int = 15
    anomaly_drift_sigma: float = 2.5  # learned-baseline z-score gate (DB-editable rule comes with the rules editor)
    chaos_auto_recover_seconds: int = 90
    ingest_token: str = ""  # internal pipeline token; dev default applied when empty
    demo_service_base_port: int = 9101
    github_token: str = ""  # optional: real PRs; otherwise patches go to LOOM
    github_repo: str = ""   # e.g. umangvijay/astraea-demo

    # ── Shield ──
    shield_detector_interval_seconds: int = 5
    shield_window_seconds: int = 120
    shield_incident_cooldown_seconds: int = 30

    neo4j_url: str = ""  # e.g. http://127.0.0.1:7474 — postgres graph fallback when empty

    # ── Vaani (voice) ──
    vaani_whisper_model: str = "base"     # faster-whisper size: tiny|base|small
    vaani_tts: str = "auto"               # auto: piper (if importable) -> macOS say
    vaani_say_voice: str = "Samantha"     # macOS voice for the say fallback
    vaani_auto_approve_bookings: bool = True
    vaani_latency_target_ms: int = 1500
    # DPDP Act: consent announced at t0; PII masked before any transcript is persisted.
    vaani_pii_masking: bool = True
    vaani_consent_notice: str = (
        "This call may be recorded and handled by an AI assistant for quality and "
        "record-keeping. Personal identifiers are masked before storage.")
    # Telephony: "exotel" enables the Exotel AgentStream translation at /ws/vaani/exotel.
    vaani_telephony: str = ""
    # Optional Indic STT/TTS (Sarvam Saaras/Bulbul); falls back to whisper/piper/say.
    sarvam_api_key: str = ""
    vaani_stt_provider: str = "auto"   # auto | whisper | sarvam
    vaani_tts_provider: str = "auto"   # auto | piper | say | sarvam

    # ── Forge / Model-Forge ──
    forge_model_path: str = ""          # set by promotion; champion served via the mlx provider
    forge_base_model: str = "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
    forge_train_iters: int = 120
    forge_train_size: int = 220         # generated training pairs
    forge_eval_size: int = 15
    forge_consolidator_interval_s: int = 86400  # nightly in production; tests override

    # ── Operator ──
    operator_parser: str = "dom"  # dom (zero-dep grounding) | omniparser (needs weights)
    operator_max_steps: int = 25
    operator_action_timeout_s: int = 12
    operator_vlm: str = "auto"    # auto: gemini -> ollama -> heuristic planner

    # ── Sentinel ──
    sentinel_overhead_target_ms: int = 120  # displayed target, measured per request
    sentinel_onnx_threshold: float = 0.85
    sentinel_similarity_threshold: float = 0.82
    tenant_monthly_token_quota: int = 2_000_000

    @property
    def demo_services(self) -> dict[str, int]:
        base = self.demo_service_base_port
        return {"checkout": base, "payments": base + 1, "inventory": base + 2}

    @property
    def effective_ingest_token(self) -> str:
        if self.ingest_token:
            return self.ingest_token
        return "dev-internal" if not self.is_production else ""

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        instance = os.environ.get("ASTRAEA_CLOUD_SQL_INSTANCE", "").strip()
        if instance:
            user = os.environ.get("ASTRAEA_DATABASE_USER", "astraea")
            password = os.environ.get("ASTRAEA_DATABASE_PASSWORD", "")
            name = os.environ.get("ASTRAEA_DATABASE_NAME", "astraea")
            from urllib.parse import quote_plus

            return (
                f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}"
                f"@/{name}?host=/cloudsql/{instance}"
            )
        return f"sqlite+aiosqlite:///{self.data_dir / 'astraea.db'}"

    data_dir_override: str = ""

    @property
    def data_dir(self) -> Path:
        if self.data_dir_override:
            return Path(self.data_dir_override)
        mounted = Path("/mnt/astraea")
        if mounted.is_dir() and os.access(str(mounted), os.W_OK):
            return mounted
        if os.environ.get("K_SERVICE"):
            path = Path("/tmp/astraea")
            path.mkdir(parents=True, exist_ok=True)
            return path
        return ROOT / "data"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def provider_order(self) -> list[str]:
        return [p.strip().lower() for p in self.llm_provider_order.split(",") if p.strip()]


settings = Settings()


def on_cloud_run() -> bool:
    """Cloud Run / Cloud Functions set K_SERVICE to the service name."""
    return bool(os.environ.get("K_SERVICE"))


def apply_production_guards() -> None:
    """Refuse a laptop production boot without secrets; on Cloud Run, boot anyway.

    Importing this module must never raise — Alembic and the Cloud Run entrypoint
    need the Settings object even when JWT/ingest env vars were omitted.
    """
    import logging as _logging
    import secrets as _secrets

    log = _logging.getLogger("astraea.config")
    vault = os.environ.get("ASTRAEA_VAULT_KEY")
    if vault and len(vault) < 32:
        raise RuntimeError("ASTRAEA_VAULT_KEY must be 32+ bytes when provided")

    if not settings.is_production:
        if not settings.jwt_secret:
            settings.jwt_secret = "ephemeral-" + _secrets.token_hex(24)
        return

    cloud = on_cloud_run()
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        if not cloud:
            raise RuntimeError("ASTRAEA_JWT_SECRET must be set (32+ chars) in production")
        settings.jwt_secret = "cloud-" + _secrets.token_hex(24)
        log.error("ASTRAEA_JWT_SECRET missing — ephemeral Cloud Run secret; sessions reset per instance")
    if not settings.ingest_token:
        if not cloud:
            raise RuntimeError("ASTRAEA_INGEST_TOKEN must be set in production")
        settings.ingest_token = "cloud-ingest-" + _secrets.token_hex(16)
        log.error("ASTRAEA_INGEST_TOKEN missing — ephemeral Cloud Run ingest token")


if not settings.jwt_secret:
    import secrets as _secrets

    settings.jwt_secret = "ephemeral-" + _secrets.token_hex(24)
    # tokens rotate on restart in dev; the launcher warns until ASTRAEA_JWT_SECRET is set
    # Cloud Run production fills a stronger secret in apply_production_guards()
