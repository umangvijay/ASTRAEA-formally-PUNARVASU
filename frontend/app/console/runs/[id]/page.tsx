"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, streamSSE } from "@/lib/api";

type Run = {
  id: string; goal: string; status: string; origin_module: string;
  result: { outputs?: Record<string, string> } | null; error: string | null;
};
type Ev = { id: number; type: string; node: string | null; payload: Record<string, unknown> | null; at: string };

const LIVE_TYPES = new Set(["run_started", "step_started", "step_completed", "run_resumed", "run_completed"]);

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const [busy, setBusy] = useState(false);
  const [stream, setStream] = useState<{ node: string; text: string } | null>(null);
  const lastId = useRef(0);
  const timeline = useRef<HTMLDivElement>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api<{ run: Run; events: Ev[] }>(`/api/runs/${runId}`);
      setRun(data.run);
      setEvents(data.events);
      lastId.current = data.events.length ? data.events[data.events.length - 1].id : 0;
      setFetchError(null);
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : "run failed to load");
    }
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    load();
    // live tail: everything after the backlog arrives via SSE in real time
    const stop = streamSSE(`/api/runs/${runId}/stream`, (ev) => {
      const type = ev.type as string;
      if (type === "caught_up") return;
      if (type === "llm_delta") {
        // live token stream — shown in the streaming panel, never in the replay list
        const node = (ev.node as string) ?? "llm";
        const text = String((ev.payload as { text?: string } | null)?.text ?? "");
        setStream((s) => (s && s.node === node ? { node, text: s.text + text } : { node, text }));
        return;
      }
      if (type === "step_completed" || type === "step_failed") setStream(null);
      setRun((r) => (ev.run_status ? { ...(r as Run), status: ev.run_status as string } : r));
      setEvents((list) =>
        ev.id && !list.some((e) => e.id === ev.id)
          ? [...list, ev as unknown as Ev]
          : list
      );
    });
    return stop;
  }, [runId, load]);

  useEffect(() => {
    timeline.current?.scrollTo({ top: timeline.current.scrollHeight });
  }, [events.length]);

  async function decide(approved: boolean) {
    setBusy(true);
    try {
      await api(`/api/runs/${runId}/approve`, { method: "POST", body: JSON.stringify({ approved }) });
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function resume() {
    setBusy(true);
    try {
      await api(`/api/runs/${runId}/resume`, { method: "POST" });
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (!run) {
    return (
      <div className="empty">
        {fetchError ? `Failed to fetch — ${fetchError}` : "loading run…"}
      </div>
    );
  }
  const atGate = run.status === "awaiting_approval";

  return (
    <>
      <div className="pagehead">
        <span className="label">
          <Link href="/console/runs">← runs</Link> · origin: {run.origin_module}
        </span>
        <h1 className="display" style={{ display: "flex", gap: 14, alignItems: "center" }}>
          <span className={`dot ${run.status === "running" ? "dot--live" : run.status === "completed" ? "" : "dot--amber"}`} />
          {run.goal}
        </h1>
        <p>
          status <b>{run.status}</b>
          {run.error ? ` — ${run.error}` : ""}
          {" · "}every line below is a persisted event — this page is a live replay.
        </p>
      </div>

      {(atGate || run.status === "interrupted" || run.status === "queued") && (
        <div className="panel panel--accent" style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
            <span className="stamp">{atGate ? "HUMAN GATE" : "PARKED"}</span>
            <span style={{ flex: 1, fontSize: 13.5, color: "var(--ink-70)" }}>
              {atGate
                ? "the run is parked at an approval gate — it will wait here across restarts until you decide."
                : "this run can resume exactly where it stopped — completed steps will not re-execute."}
            </span>
            {atGate ? (
              <>
                <button className="btn btn--accent" disabled={busy} onClick={() => decide(true)}>Approve →</button>
                <button className="btn" disabled={busy} onClick={() => decide(false)}>Reject</button>
              </>
            ) : (
              <button className="btn btn--accent" disabled={busy} onClick={resume}>Resume →</button>
            )}
          </div>
        </div>
      )}

      <div ref={timeline} className="panel sheet" style={{ maxHeight: 420, overflowY: "auto", fontFamily: "var(--font-mono)", fontSize: 12.5 }}>
        {events.map((e) => (
          <div key={e.id} style={{ padding: "7px 4px", borderBottom: "1px dotted var(--line)", display: "flex", gap: 12 }}>
            <span style={{ color: "var(--ink-30)", minWidth: 34 }}>#{e.id}</span>
            <span style={{ minWidth: 150, color: LIVE_TYPES.has(e.type) ? "var(--accent)" : "var(--ink-70)" }}>
              {e.type}
            </span>
            <span style={{ minWidth: 90, color: "var(--slate)" }}>{e.node ?? "—"}</span>
            <span style={{ color: "var(--ink-70)", wordBreak: "break-all" }}>
              {e.payload ? JSON.stringify(e.payload).slice(0, 160) : ""}
            </span>
          </div>
        ))}
        {events.length === 0 && <div className="empty">no events yet…</div>}
      </div>

      {stream && (
        <div className="panel" style={{ marginTop: 20, borderColor: "var(--accent)" }}>
          <p className="label label--accent">live output — {stream.node} (streaming via sentinel)</p>
          <pre style={{ margin: "8px 0 0", fontFamily: "var(--font-mono)", fontSize: 12.5,
                        whiteSpace: "pre-wrap", background: "var(--paper-dim)", padding: 12,
                        maxHeight: 240, overflowY: "auto" }}>
            {stream.text}
          </pre>
        </div>
      )}

      {run.result?.outputs && (
        <div className="panel" style={{ marginTop: 20 }}>
          <p className="label label--ink">outputs</p>
          {Object.entries(run.result.outputs).map(([k, v]) => (
            <div key={k} style={{ marginTop: 10 }}>
              <p className="label">{k}</p>
              <pre style={{ margin: "4px 0 0", fontFamily: "var(--font-mono)", fontSize: 12.5,
                            whiteSpace: "pre-wrap", background: "var(--paper-dim)", padding: 12 }}>
                {String(v)}
              </pre>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
