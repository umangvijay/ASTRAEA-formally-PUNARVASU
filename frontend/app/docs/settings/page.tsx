export default function Doc() {
  return (
    <>
      <span className="label label--accent">SETTINGS · VAULT · SECURITY</span>
      <h1 className="display">Your workspace, your controls.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Five tabs: Workspace (which agents run), Profile (what every agent knows about
        your business), Sharing (who may read Memory), Vault (encrypted secrets) and
        Security (API keys + the audit trail).
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>Workspace — SOLO vs FUSION</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>FUSION</b> — every agent runs; cross-module workflows allowed. The default.</li>
        <li><b>SOLO</b> — pick exactly one agent (MEDIC only, for example). Its detectors run; the others idle.</li>
        <li><b>Memory is shared in both modes.</b> That&apos;s the whole point: run SHIELD alone for a month, switch on MEDIC tomorrow — it already knows everything. Nothing is ever re-entered.</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>Vault — encrypted secrets</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Save credentials once (API keys, tokens, passwords). They&apos;re encrypted with
        <b> AES-256-GCM</b> before touching the disk — the database stores only ciphertext.
        Reading one back is a deliberate <b>REVEAL</b> action, and every reveal is written to
        the security audit trail. The encryption key comes from <span className="mono">ASTRAEA_VAULT_KEY</span>
        (set your own 32-byte key in production).
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>Security — the audit trail</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Every login (success and failure), vault access, and account event is recorded with
        time, action and IP. Failed logins lock the account for 15 minutes after 5 attempts.
        Passwords are hashed with Argon2id. Your tenant API key (for calling Sentinel&apos;s
        OpenAI-compatible endpoint) lives here too, with one-click rotation.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div><b>Workspace</b> — click FUSION, or click one agent for SOLO mode.</div></div>
        <div className="docs-step"><span className="n">2</span><div><b>Profile</b> — fill company/stack/compliance once; every agent reads it.</div></div>
        <div className="docs-step"><span className="n">3</span><div><b>Vault</b> — store a secret, note that reveal is the exception, not the habit.</div></div>
        <div className="docs-step"><span className="n">4</span><div><b>Security</b> — review the audit trail; rotate the API key if it ever leaked.</div></div>
      </div>
    </>
  );
}
