import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import PublicChrome from "../components/PublicChrome";
import { type Camera, type Palette, readPalette } from "../twin/map3d/palette";
import { demoBoard } from "../twin/board3d/model";
import { hasWebGL, reducedMotion } from "../twin/board3d/StepVisual";
import "../twin/board3d/board3d.css";

const Board3DView = lazy(() => import("../twin/board3d/Board3DView"));

const OUTPUTS: [string, string][] = [
  ["Speed", "Latency per frame and how many inputs a second the board can keep up with."],
  ["Memory", "Working memory and weight storage, tensor by tensor, against what the device has."],
  ["Power and energy", "Average and peak power, and energy per inference, for every power mode."],
  ["Heat and throttling", "Steady temperature with your cooling, and whether the chip will slow itself down."],
  ["Cost and carbon", "Electricity cost and emissions per day, from the energy figures."],
  ["What to change", "The changes that fix it, ranked, with side-by-side plans."],
];

const HARDWARE: [string, string][] = [
  ["Microcontrollers", "STM32, ESP32 and other MCUs for keyword spotting and tiny vision"],
  ["Edge boards", "Jetson, Raspberry Pi and other boards with a GPU or NPU"],
  ["FPGAs", "Kria and similar boards running quantised models"],
  ["Data-centre GPUs", "L4, L40S, H100 and other accelerators, for throughput and cost"],
];

const CAM: Camera = { azimuth: 0.7, elevation: 0.58, distance: 1.95 };

function HeroScene() {
  const [webgl] = useState(hasWebGL);
  const [motion] = useState(() => !reducedMotion());
  const [visible, setVisible] = useState(true);
  const [pal] = useState<Palette>(readPalette);
  const board = useMemo(demoBoard, []);
  const none = useMemo(() => new Set<string>(), []);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!box.current || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting));
    io.observe(box.current);
    return () => io.disconnect();
  }, []);
  const words = "Illustration: a circuit board with a fan-cooled chip and a floating heat map above it, hottest over the chip.";
  return (
    <div className="gl-canvas" ref={box} role="img" aria-label={words}>
      {webgl ? (
        <Suspense fallback={<div className="gl-fallback">Loading the 3D view…</div>}>
          <Board3DView boards={[board]} temps={[board.tempC]} scaleMaxC={board.throttleC + 8} cam={CAM} pal={pal} animate={motion && visible} explode={0} showHeat showCircuit
            showFlow showLabels={false} limit={false} activeIds={none} glowKinds={none} spin />
        </Suspense>
      ) : (
        <div className="gl-fallback">{words}</div>
      )}
    </div>
  );
}

export default function LandingPage({ signedIn = false }: { signedIn?: boolean }) {
  return (
    <PublicChrome signedIn={signedIn} className="pub-glass">
      <section className="gl-hero" aria-labelledby="hero-title">
        <div>
          <p className="gl-kicker">Free while in early access</p>
          <h1 id="hero-title">Will your AI model run on your hardware? <em>Find out before you build it.</em></h1>
          <p className="gl-lead">
            Predict speed, memory, power, heat, energy, cost and carbon for an AI model on a specific board or chip.
            See what limits it and which change fixes it. Every number has a range and says whether it was predicted or measured.
          </p>
          <div className="pub-cta">
            <a className="btn-link primary" href="#/try">Try an example, no account needed</a>
            <a className="btn-link" href={signedIn ? "#/" : "#/signup"}>{signedIn ? "Open your workspace" : "Create a free account"}</a>
          </div>
          <p className="gl-hint">Your models are analysed, never run on our servers. Predictions are not yet validated on every board, so check them on real hardware before you rely on them.</p>
        </div>
        <figure className="gl-glass gl-stage" style={{ margin: 0 }}>
          <HeroScene />
          <figcaption className="gl-cap">Illustration, not a real board or a real result. The same view in the app uses the engine's numbers for your setup.</figcaption>
        </figure>
      </section>

      <section className="gl-section" aria-labelledby="how-title">
        <h2 id="how-title">How it works</h2>
        <ol className="gl-steps">
          <li className="gl-glass"><strong>Describe the job</strong> Pick a model and a board, or upload an ONNX model and enter your own hardware. Say what matters: speed, power, heat or cost.</li>
          <li className="gl-glass"><strong>We search thousands of setups</strong> Precision, batch size, power mode, cooling, input size and pruning, each checked against your requirements.</li>
          <li className="gl-glass"><strong>You get a plain answer</strong> Whether it works today, what limits it, the change to make, and a report to hand over.</li>
          <li className="gl-glass"><strong>Check it on the real device</strong> Import a benchmark log or pair your own board, and the predictions are corrected with your measurements.</li>
        </ol>
      </section>

      <section className="gl-section" aria-labelledby="out-title">
        <h2 id="out-title">What you find out</h2>
        <ul className="gl-grid">
          {OUTPUTS.map(([t, d]) => <li key={t} className="gl-glass gl-card"><h3>{t}</h3><p>{d}</p></li>)}
        </ul>
      </section>

      <section className="gl-section" aria-labelledby="honest-title">
        <div className="gl-glass gl-honest">
          <h2 id="honest-title" style={{ marginTop: 0 }}>Honest numbers</h2>
          <p>Predictions come from a physics model of compute, memory traffic, power and heat. They are labelled <strong>predicted</strong> and shown with a best-to-worst-case range. Numbers from a real run are labelled <strong>measured</strong>, and the two are never mixed up.</p>
          <p><a href="#/how">Read how we estimate, and what we do not model →</a></p>
        </div>
      </section>

      <section className="gl-section" aria-labelledby="hw-title">
        <h2 id="hw-title">From microcontrollers to data-centre GPUs</h2>
        <ul className="gl-grid">
          {HARDWARE.map(([t, d]) => <li key={t} className="gl-glass gl-card"><h3>{t}</h3><p>{d}</p></li>)}
        </ul>
        <p className="gl-hint">Not in the library? Enter a board's figures yourself, or read them from its datasheet PDF and confirm each value.</p>
      </section>

      <section className="gl-section" aria-labelledby="final-title">
        <div className="gl-glass gl-final">
          <h2 id="final-title">See a full analysis</h2>
          <p>Six worked examples, from a voice command on a microcontroller to a cloud detection service.</p>
          <div className="pub-cta">
            <a className="btn-link primary" href="#/try">Try an example</a>
            {!signedIn && <a className="btn-link" href="#/signup">Create a free account</a>}
          </div>
        </div>
      </section>
    </PublicChrome>
  );
}
