"use client";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main style={{ minHeight: "60vh", display: "grid", placeItems: "center", padding: 32 }}>
      <div>
        <p className="label label--accent">PAGE FAILED</p>
        <h1 className="display" style={{ fontSize: 32 }}>This plate crashed.</h1>
        <p style={{ color: "var(--ink-70)" }}>{error.message}</p>
        <button className="btn btn--accent" type="button" onClick={reset}>Try again</button>
      </div>
    </main>
  );
}
