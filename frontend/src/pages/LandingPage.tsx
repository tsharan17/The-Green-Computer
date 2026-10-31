import PublicChrome from "../components/PublicChrome";

const OUTPUTS: [string, string][] = [
  ["Speed", "Latency per frame and how many inputs a second the board can keep up with."],
  ["Memory", "Working memory and weight storage, tensor by tensor, against what the device has."],
  ["Power and energy", "Average and peak power, and energy per inference, for every power mode."],
  ["Heat and throttling", "Steady temperature with your cooling, and whether the chip will slow itself down."],
  ["Cost and carbon", "Electricity cost and emissions per day, from the energy figures."],
  ["What to change", "The one change that fixes it, ranked options, and side-by-side plans."],
];

const HARDWARE: [string, string][] = [
  ["Microcontrollers", "STM32, ESP32 and other MCUs for keyword spotting and tiny vision"],
  ["Edge boards", "Jetson, Raspberry Pi and other boards with a GPU or NPU"],
  ["FPGAs", "Kria and similar boards running quantised models"],
  ["Data-centre GPUs", "L4, L40S, H100 and other accelerators, for throughput and cost"],
];

export default function LandingPage({ signedIn = false }: { signedIn?: boolean }) {
  return (
    <PublicChrome signedIn={signedIn}>
      <section className="pub-hero" aria-labelledby="hero-title">
        <div>
          <h1 id="hero-title">Will your AI model run well on your hardware? Find out before you build it.</h1>
          <p className="pub-lead">
            The Green Computer predicts speed, memory, power, heat, energy, cost and carbon for an AI model on a
            specific board or chip, tells you what limits it, and recommends the change that fixes it. Every number
            comes with a range and says whether it was predicted or measured.
          </p>
          <div className="pub-cta">
            <a className="btn-link primary" href="#/try">Try an example, no account needed</a>
            <a className="btn-link" href={signedIn ? "#/" : "#/signup"}>{signedIn ? "Open your workspace" : "Create a free account"}</a>
          </div>
          <p className="hint">Free while in early access. Your models are analysed, never run on our servers.</p>
        </div>
        <figure className="auth-example pub-example" aria-label="Illustration of a result">
          <figcaption>What a result looks like (illustration)</figcaption>
          <p className="ae-row"><span>Today</span> <span className="outcome bad"><span aria-hidden className="outcome-icon">✕</span> Fails</span>
            <span aria-hidden>→</span><span>With the plan</span> <span className="outcome ok"><span aria-hidden className="outcome-icon">✓</span> Passes</span></p>
          <p className="ae-line">YOLOv8s on a Jetson Orin NX gets too hot at 40 °C with passive cooling.</p>
          <p className="ae-line"><strong>Do this:</strong> switch to INT8 and the 25 W power mode.</p>
          <p className="hint">Predicted, with a range. Measured once you run it on the device.</p>
        </figure>
      </section>

      <section className="pub-section" aria-labelledby="how-title">
        <h2 id="how-title">How it works</h2>
        <ol className="pub-steps">
          <li><strong>Describe the job.</strong> Pick a model and a board from the library, or upload an ONNX model and enter your own hardware. Say what matters: speed, power, heat or cost.</li>
          <li><strong>We search thousands of setups.</strong> Precision, batch size, power mode, cooling, input size and pruning, each checked against your requirements.</li>
          <li><strong>You get a plain answer.</strong> Whether it works today, what limits it, the change to make, and a report to hand over.</li>
          <li><strong>Check it on the real device.</strong> Import a benchmark log or pair your own board, and the predictions are corrected with your measurements.</li>
        </ol>
      </section>

      <section className="pub-section" aria-labelledby="out-title">
        <h2 id="out-title">What you find out</h2>
        <ul className="pub-grid">
          {OUTPUTS.map(([t, d]) => (
            <li key={t} className="pub-card"><h3>{t}</h3><p>{d}</p></li>
          ))}
        </ul>
      </section>

      <section className="pub-section pub-honest" aria-labelledby="honest-title">
        <h2 id="honest-title">Honest numbers</h2>
        <p>
          Predictions come from a physics model of compute, memory traffic, power and heat. They are labelled{" "}
          <strong>predicted</strong> and shown with a best-to-worst-case range. Numbers from a real run are labelled{" "}
          <strong>measured</strong>, and the two are never mixed up. When you add measurements, the model is calibrated
          to your device and says so.
        </p>
        <p><a href="#/how">Read how we estimate, and what we do not model →</a></p>
      </section>

      <section className="pub-section" aria-labelledby="hw-title">
        <h2 id="hw-title">From microcontrollers to data-centre GPUs</h2>
        <ul className="pub-grid pub-grid-4">
          {HARDWARE.map(([t, d]) => (
            <li key={t} className="pub-card"><h3>{t}</h3><p>{d}</p></li>
          ))}
        </ul>
        <p className="hint">Not in the library? Enter a board's figures yourself, or read them from its datasheet PDF and confirm each value.</p>
      </section>

      <section className="pub-section pub-final" aria-labelledby="final-title">
        <h2 id="final-title">See a full analysis in a few seconds</h2>
        <p>Six worked examples, from a voice command on a microcontroller to a cloud detection service.</p>
        <div className="pub-cta">
          <a className="btn-link primary" href="#/try">Try an example</a>
          {!signedIn && <a className="btn-link" href="#/signup">Create a free account</a>}
        </div>
      </section>
    </PublicChrome>
  );
}
