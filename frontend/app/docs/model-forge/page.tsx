export default function Doc() {
  return (
    <>
      <span className="label label--accent">MODEL-FORGE · OUR OWN MODEL</span>
      <h1 className="display">A model we trained ourselves.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        MODEL-FORGE is a text-to-SQL model post-trained in-house (LoRA fine-tune on
        verifiable rewards) and served locally on Apple Silicon — no API key, no cloud,
        registered in Sentinel as just another provider in the fallback chain.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What you use it for</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>A brain that always works</b> — with no Gemini/Groq keys and no internet, the platform still has a real model answering (it powers the demo&apos;s AI steps out of the box).</li>
        <li><b>Proprietary edge</b> — the weights are ours, trained on our generated data, improved by FORGE.</li>
        <li><b>Verifiable skill</b> — its exam is text-to-SQL: the query must execute and return the exact gold rows. Score 11/15 = 73% today; the Colab scale-up (Qwen2.5-3B/7B + GRPO) is the ≥90% path.</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How it works</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        A generator creates unlimited question/SQL/gold-rows triples from a demo schema —
        every answer is checkable by running the query. Training data becomes JSONL
        (SFT format); <span className="mono">python -m app.model_forge.train</span> runs MLX LoRA
        on this Mac; the champion is saved under <span className="mono">data/forge/model</span> and
        served in-process. In Sentinel&apos;s provider chain it sits after the cloud options:
        gemini → groq → ollama → <b>model_forge</b> → base MLX. Explicit model hints
        (<span className="mono">pvu-sql</span>) route to it directly — e.g. MEDIC&apos;s SQL analysis.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div>Open <b>MODEL-FORGE</b> — serving status, weights path and benchmark history are live.</div></div>
        <div className="docs-step"><span className="n">2</span><div>Click <b>Re-run benchmark →</b> — it takes the 15-task held-out exam and shows the score.</div></div>
        <div className="docs-step"><span className="n">3</span><div>Retrain any time with <span className="mono">python -m app.model_forge.train</span> — then re-benchmark; the eval history keeps the record.</div></div>
      </div>
    </>
  );
}
