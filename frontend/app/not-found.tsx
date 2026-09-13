import Link from "next/link";

export default function NotFound() {
  return (
    <main style={{ minHeight: "70vh", display: "grid", placeItems: "center", padding: 32 }}>
      <div style={{ maxWidth: 480 }}>
        <p className="label label--accent">404</p>
        <h1 className="display" style={{ fontSize: 36, margin: "8px 0 12px" }}>This plate is blank.</h1>
        <p style={{ color: "var(--ink-70)", marginBottom: 18 }}>
          No page, no module, no fake workbench. The route does not exist.
        </p>
        <Link href="/" className="btn btn--accent">Back to the sky map</Link>
      </div>
    </main>
  );
}
