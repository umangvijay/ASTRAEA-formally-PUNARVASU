"use client";

export default function DocsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div>
      <p className="label label--accent">DOCS PAGE FAILED</p>
      <h1 className="display" style={{ fontSize: 28 }}>This article crashed.</h1>
      <p style={{ color: "var(--ink-70)" }}>{error.message}</p>
      <button className="btn btn--accent" type="button" onClick={reset}>Try again</button>
    </div>
  );
}
