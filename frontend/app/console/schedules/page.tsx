import Link from "next/link";

export default function SchedulesHint() {
  return (
    <>
      <div className="pagehead">
        <span className="label label--accent">NOT SHIPPED</span>
        <h1 className="display">No cron table yet.</h1>
        <p>
          MASTER_SPEC mentions schedules. This build has leased workers and
          Fusion runs — not a schedules API. Start a job now, or come back when
          cron lands.
        </p>
        <p style={{ marginTop: 16 }}>
          <Link href="/console/fusion" className="btn btn--accent">Open Fusion →</Link>
        </p>
      </div>
    </>
  );
}
