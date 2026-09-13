import { PipelineDiagram, StackDiagram } from "@/components/ArchDiagram";

export default function Doc() {
  return (
    <>
      <span className="label label--accent">SECURITY · ENCRYPTION</span>
      <h1 className="display serif">Hard on the outside. Honest inside.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Passwords, vault, model traffic and tool egress are production controls —
        not a marketing checklist. Full write-up: <span className="mono">docs/SECURITY.md</span>.
      </p>

      <PipelineDiagram
        title="AUTH + VAULT"
        stages={[
          { id: "argon2id", label: "Passwords", detail: "Argon2id, 64MB, time_cost=3. Legacy scrypt upgrades on next login." },
          { id: "lockout", label: "Lockout", detail: "5 failures per email+IP → 15 minutes (HTTP 423). Every attempt audited." },
          { id: "jwt", label: "Session", detail: "HS256 JWT with jti. Production refuses to boot without ASTRAEA_JWT_SECRET." },
          { id: "gcm", label: "Vault", detail: "AES-256-GCM. ASTRAEA_VAULT_KEY (32 bytes) or scrypt-derived from the JWT secret. Do not change the KDF — it would invalidate ciphertext." },
          { id: "reveal", label: "Reveal", detail: "Plaintext only via the explicit reveal API. Every reveal is an audit event." },
        ]}
      />

      <StackDiagram />

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What else is on</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>SENTINEL</b> — every model call: injection / jailbreak / Indic-PII scan, streaming output scan, per-tenant quota.</li>
        <li><b>SSRF guards</b> — <span className="mono">http_get</span> and <span className="mono">web.fetch</span> refuse localhost and RFC1918.</li>
        <li><b>Tool sandbox</b> — shell/code in a no-network Docker/gVisor box; loud host-rlimit fallback.</li>
        <li><b>CSP + security headers</b> on every HTTP response.</li>
        <li><b>DPDP</b> — VAANI announces consent at t0; Aadhaar/PAN/phone/card/email masked before persist.</li>
      </ul>
    </>
  );
}
