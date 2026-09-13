import { FlowDiagram, PipelineDiagram } from "@/components/ArchDiagram";

export default function Doc() {
  return (
    <>
      <span className="label label--accent">DEPLOY · OFFLINE + GCLOUD</span>
      <h1 className="display serif">One build. Three places.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        The same tree runs on a laptop with no keys, on Google Cloud with Vertex AI,
        and later on AWS. Nothing in the code names a single cloud as destiny.
        Runbook twin: <span className="mono">docs/DEPLOY.md</span>.
      </p>

      <FlowDiagram
        title="PROVIDER CHAIN"
        steps={[
          { id: "vertex", label: "Vertex" },
          { id: "gemini", label: "Studio" },
          { id: "claude", label: "Claude" },
          { id: "groq", label: "Groq" },
          { id: "ollama", label: "Ollama" },
        ]}
      />

      <PipelineDiagram
        title="GCLOUD PATH"
        stages={[
          { id: "project", label: "Project", detail: "ASTRAEA_VERTEX_PROJECT + location (default us-central1)." },
          { id: "auth", label: "Auth", detail: "ADC, ASTRAEA_VERTEX_ACCESS_TOKEN, or ASTRAEA_VERTEX_API_KEY." },
          { id: "sentinel", label: "Route", detail: "SENTINEL picks vertex when the project is ready — same Gemini models, billed to GCP." },
          { id: "fallback", label: "Offline", detail: "No project? Ollama / MODEL-FORGE / MLX still answer. Never a canned string." },
        ]}
      />

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>Local</h2>
      <div className="code-block">{`cp .env.example .env
# optional: ollama pull llama3.2
python3 main.py
# http://localhost:3000`}</div>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>GCloud (Vertex + Cloud Run)</h2>
      <div className="code-block">{`# Full commands: docs/DEPLOY.md
# Browser → console /api/astraea/* → API → Vertex. No canned replies.

gcloud builds submit --config deploy/cloudbuild.api.yaml
gcloud run deploy astraea-api --image gcr.io/YOUR_PROJECT/astraea-api \\
  --allow-unauthenticated --memory 1Gi --region us-central1 \\
  --set-env-vars ASTRAEA_ENV=production,ASTRAEA_VERTEX_PROJECT=YOUR_PROJECT,ASTRAEA_JWT_SECRET=…,ASTRAEA_INGEST_TOKEN=…

gcloud builds submit --config deploy/cloudbuild.console.yaml
gcloud run deploy astraea-console --image gcr.io/YOUR_PROJECT/astraea-console \\
  --allow-unauthenticated --region us-central1 \\
  --set-env-vars ASTRAEA_USE_API_PROXY=1,ASTRAEA_PUBLIC_API_URL=https://astraea-api-….run.app`}</div>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Cloud Run attaches ADC automatically — no access token in env if the
        service account can call Vertex (<span className="mono">roles/aiplatform.user</span>).
        The console proxies the API so guest login is not a cross-origin
        <span className="mono">Failed to fetch</span>. AWS later is the same binary plus env: point
        <span className="mono">ASTRAEA_DATABASE_URL</span> at RDS. No rewrite.
      </p>
    </>
  );
}
