import { PublicNav } from "@/components/PublicNav";

const FAQS = [
  ["Do I need API keys?", "Chat and research need a general brain: Vertex (ASTRAEA_VERTEX_PROJECT + ADC), Gemini, Groq, or Ollama. The SQL champion is never the default. Offline tools (runs, vault, Fusion recipes without LLM) still work with no key."],
  ["What does 'durable' mean?", "Agent runs are event-sourced: every step is persisted. If the process crashes mid-run, the run is marked interrupted and resumes exactly where it stopped — finished steps never re-execute."],
  ["Can the agents share what they learn?", "Yes — everything flows through LOOM, the shared context fabric, stamped with provenance (FROM SHIELD / USED BY MEDIC). Start with one product today, adopt others tomorrow, zero re-onboarding."],
  ["Is my data secure?", "Every LLM call passes SENTINEL. Passwords are Argon2id (legacy scrypt upgrades on login). Vault is AES-256-GCM. Security headers ship by default."],
  ["Can I self-host?", "Yes — the whole platform is open-source, runs on your machine with one command, and talks to no external service unless you configure one."],
  ["What is the guest mode?", "A 30-minute time-boxed workspace with the full platform, no sign-up. After it expires, create an account and your guest data migrates forward via LOOM."],
  ["What are the roles?", "guest (30 min, full platform) → user (your workspace) → admin (fleet overview, user management) → superadmin (everything including system rules). Roles are set on the user model and gate admin-only endpoints."],
  ["How does the security gateway work?", "SENTINEL is a reverse proxy every LLM call passes through. Input scanning catches injection, jailbreak and Indic-PII patterns; output scanning redacts mid-stream so PII split across tokens is still caught. Rules are DB rows, editable per tenant."],
  ["What if a service goes down?", "Every external dependency has a defined fallback: cloud LLM → local model → graceful degradation message. The platform never crashes silently — the console shows which services are healthy in real time."],
  ["Can I see what the agents did?", "Yes — every run is event-sourced: each step is persisted with payloads and costs. The Runs page shows the full timeline, and you can replay from any event. Agents also write postmortems and artifacts into LOOM with provenance stamps."],
  ["What is the shared memory (LOOM)?", "LOOM is the context fabric: one store where every agent writes what it learns, stamped with origin (FROM SHIELD) and usage (USED BY MEDIC). Switch products tomorrow — everything is already known, no re-onboarding."],
  ["How does the self-evolving engine work?", "FORGE mines failures from real agent runs, proposes new tools or prompt patches, evaluates them on a verifiable task suite and promotes only measured improvements — every change committed to the agent's own git repo."],
  ["Is the voice agent real-time?", "VAANI in this build is a browser WebSocket + ScriptProcessor. Exotel/PSTN only if you set ASTRAEA_VAANI_TELEPHONY. The <100ms barge-in number is a target, not a published load-test."],
  ["What themes are available?", "Night (observatory — charcoal sky, cream plates, oxide labels) and Day (cream paper over the same sky). Toggle from the nav; your choice persists."],
];

export default function FAQ() {
  return (
    <>
      <PublicNav />
      <section className="hero">
        <div className="observatory-plaque">
          <span className="label label--accent">FAQ</span>
          <h1 className="display" style={{ marginTop: 12 }}>Questions, answered.</h1>
        </div>
      </section>
      <section className="section" style={{ paddingTop: 10 }}>
        {FAQS.map(([q, a]) => (
          <div key={q} className="faq-item">
            <h3>{q}</h3>
            <p>{a}</p>
          </div>
        ))}
      </section>
      <footer className="site-footer">
        <span className="label">© 2026 Astraea</span>
      </footer>
    </>
  );
}
