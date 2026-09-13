export function PageError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="glass-card" style={{ margin: "0 0 16px", padding: "10px 14px" }}>
      <span className="label label--accent">API ERROR</span>
      <p style={{ margin: "4px 0 0", fontSize: 13 }}>{message}</p>
    </div>
  );
}
