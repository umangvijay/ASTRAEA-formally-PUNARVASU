# ASTRAEA — Architecture

The control plane is one process tree: FastAPI + durable workers + the Blueprint
console. Offline on a laptop; the same binary on GCloud (Vertex) or later AWS.

Console twin: `/docs/architecture`.

## Control plane stack

```mermaid
flowchart TB
  UI[Blueprint console · SOLO / FUSION]
  API[FastAPI · JWT · CSP]
  SEN[SENTINEL · Vertex / Gemini / Claude / Groq / Ollama]
  CORE[astra-core · leased workers · sandboxed tools]
  LOOM[LOOM · provenance memory]
  PULSE[PULSE · OTLP → SQLite / ClickHouse]
  UI --> API --> SEN --> CORE
  CORE --> LOOM
  CORE --> PULSE
  PULSE --> MEDIC[MEDIC]
  PULSE --> SHIELD[SHIELD]
```

## Request path

```mermaid
sequenceDiagram
  participant You
  participant Console
  participant API
  participant SENTINEL
  participant Worker
  participant LOOM
  You->>Console: live goal
  Console->>API: POST /api/...
  API->>SENTINEL: scan + route provider
  SENTINEL->>Worker: leased run
  Worker->>LOOM: stamped write
  Worker-->>Console: SSE events
```

## OPERATOR web pipeline

```mermaid
flowchart LR
  Q[goal] --> S[web.search]
  S --> F[web.fetch]
  F --> L[SENTINEL fold]
  L --> M[LOOM stamp]
```

Walled gardens (Google, ChatGPT, Claude, Cursor, GitHub login walls) skip the
headless click-loop after a successful research pack — those sites all produce
the same empty "gave up" screenshot. Public HTML is fetched per URL instead.

## Products

| Codename | Job |
|---|---|
| MEDIC | AI SRE on PULSE |
| OPERATOR | Live web + vision computer-use |
| SHIELD | AI SOC, MITRE, blast radius |
| VAANI | Voice employee, DPDP-masked |
| FORGE | Nightly skill promotion |
| MODEL-FORGE | Domain SQL model behind SENTINEL |
