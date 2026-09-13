import Link from "next/link";

export default function IntegrationsHint() {
  return (
    <>
      <div className="pagehead">
        <span className="label label--accent">NOT A SEPARATE PRODUCT</span>
        <h1 className="display">Keys live in Settings.</h1>
        <p>
          There is no <span className="mono">/api/integrations</span> router.
          Vertex, vault secrets and provider keys are on Settings. GitHub for
          MEDIC PRs is env (<span className="mono">ASTRAEA_GITHUB_TOKEN</span>).
        </p>
        <p style={{ marginTop: 16 }}>
          <Link href="/console/settings" className="btn btn--accent">Open Settings →</Link>
        </p>
      </div>
    </>
  );
}
