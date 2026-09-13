export default function Doc() {
  return (
    <>
      <span className="label label--accent">VAANI · VOICE AI EMPLOYEE</span>
      <h1 className="display">Answers the phone. Does the work.</h1>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        VAANI is a full-duplex voice agent: it listens while you talk, understands, acts —
        and the booking it takes becomes a real, durable record, not just a chat reply.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>What you use it for</h2>
      <ul style={{ color: "var(--ink-70)", fontSize: 14.5, lineHeight: 1.8 }}>
        <li><b>Take bookings by voice</b> — &quot;book a haircut tomorrow at 3pm for Ravi&quot; becomes a confirmed booking row, a Memory artifact, and a durable run.</li>
        <li><b>Natural conversation</b> — it knows your business profile and everything in Memory, so it answers with your context.</li>
        <li><b>Barge-in</b> — start talking while VAANI is speaking and it cancels its reply immediately and listens to you.</li>
      </ul>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How it works</h2>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>
        Your microphone streams 16 kHz audio over a WebSocket. Silero VAD (with an energy
        floor) detects speech in real time; faster-whisper transcribes each utterance; the
        brain answers through Sentinel with your Memory context; macOS <span className="mono">say</span>
        (or Piper) speaks the reply sentence-by-sentence. Latency — STT, brain, total — is
        measured per utterance and shown live against the 1.5 s target.
      </p>

      <h2 className="display" style={{ fontSize: 21, marginTop: 30 }}>How to use it</h2>
      <div className="docs-steps">
        <div className="docs-step"><span className="n">1</span><div>Open <b>VAANI</b>, click <b>Call ☎</b>, allow the microphone.</div></div>
        <div className="docs-step"><span className="n">2</span><div>Say: <i>&quot;Hi, I want to book a haircut for tomorrow at 3pm. My name is Ravi.&quot;</i></div></div>
        <div className="docs-step"><span className="n">3</span><div>Watch the transcript, the latency panel, and the booking appear — then find it in Memory stamped FROM VAANI.</div></div>
      </div>
      <p style={{ color: "var(--ink-70)", fontSize: 15 }}>Transcripts are saved per call. Talk over VAANI any time — barge-in cancels the reply mid-sentence.</p>
    </>
  );
}
