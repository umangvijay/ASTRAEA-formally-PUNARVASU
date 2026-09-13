import Link from "next/link";

export default function StudioHint() {
  return (
    <>
      <div className="pagehead">
        <span className="label label--accent">NOT A SEPARATE PRODUCT</span>
        <h1 className="display">Studio is Chat + Fusion.</h1>
        <p>
          There is no studio workbench. Talk through SENTINEL in Chat. Start
          durable jobs in Fusion.
        </p>
        <p style={{ marginTop: 16, display: "flex", gap: 10 }}>
          <Link href="/console/chat" className="btn btn--accent">Open Chat →</Link>
          <Link href="/console/fusion" className="btn">Open Fusion →</Link>
        </p>
      </div>
    </>
  );
}
