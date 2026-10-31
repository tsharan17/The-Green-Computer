import PublicChrome from "../components/PublicChrome";

const LABELS: [string, string][] = [
  ["Measured", "From a real run: a benchmark log you imported, or a job on a device you paired. Never produced by the model."],
  ["Predicted · checked against real runs", "A prediction corrected with your measurements for that device and precision (calibrated)."],
  ["Predicted", "The physics model's estimate, shown with a best-to-worst-case range."],
  ["From published specs", "Copied from the manufacturer's figures for the device."],
  ["Rough estimate", "A stated assumption, such as an accuracy prior or a constant the datasheet does not give."],
  ["From a datasheet, unconfirmed", "Read from a PDF by pattern and waiting for a person to confirm it. Never used in an analysis until confirmed."],
];

export default function HowPage({ signedIn = false }: { signedIn?: boolean }) {
  return (
    <PublicChrome signedIn={signedIn}>
      <article className="pub-section pub-prose" aria-labelledby="how-h1">
        <h1 id="how-h1">How we estimate</h1>
        <p className="pub-lead">
          The Green Computer predicts how a model will behave on a device from physics and published figures, then
          corrects itself with real measurements when you have them. This page says how, and what it does not cover.
        </p>

        <h2>Every number says where it came from</h2>
        <div className="table-wrap">
          <table className="tbl">
            <thead><tr><th scope="col">Label</th><th scope="col">Meaning</th></tr></thead>
            <tbody>{LABELS.map(([l, m]) => <tr key={l}><th scope="row">{l}</th><td>{m}</td></tr>)}</tbody>
          </table>
        </div>
        <p>A prediction is never shown as a measurement. When both exist, both are shown, side by side and labelled.</p>

        <h2>How a prediction is made</h2>
        <ul>
          <li><strong>Speed.</strong> Each layer's time is set by whichever is slower, its arithmetic or its memory traffic, at the
            device's achievable throughput for that precision, with imperfect overlap between the two and a fixed launch cost per
            layer (a per-layer roofline). Uploaded ONNX models are analysed layer by layer; library models without a graph are
            treated as one layer.</li>
          <li><strong>Memory.</strong> Working memory follows tensor lifetimes through the graph; weight storage follows the precision.</li>
          <li><strong>Power.</strong> Idle power, plus dynamic power that scales with clock and utilisation, plus memory power,
            plus leakage that grows with temperature. Average power accounts for how much of the time the device is busy at your
            frame rate.</li>
          <li><strong>Heat.</strong> A lumped thermal model: temperature rises above ambient by power times the cooling's thermal
            resistance, with a warm-up curve from its heat capacity.</li>
          <li><strong>Throttling.</strong> Power, temperature and leakage are solved together until they settle. If the chip would pass
            its throttle point, the clock is lowered to the highest speed that holds the limit, and speed and power are recomputed.
            So throttling is inside the prediction, not a warning added afterwards.</li>
          <li><strong>Cost and carbon.</strong> Energy over your operating hours, times an electricity price and a grid carbon
            intensity (defaults 0.15 per kWh and 400 g CO₂ per kWh; change them in a project).</li>
        </ul>

        <h2>Where the range comes from</h2>
        <p>
          Uncertain inputs, such as achievable efficiency and power constants, are pushed to an optimistic and a pessimistic
          corner and the whole coupled model is solved again at each. That gives every figure a best-to-worst-case range that
          already includes the effect on throttling.
        </p>
        <p>
          A requirement <strong>passes</strong> only if the worst case passes, <strong>fails</strong> only if even the best case
          fails, and is <strong>uncertain</strong> otherwise. Limits are never relaxed to make a setup look better.
        </p>

        <h2>Searching for a better setup</h2>
        <p>
          Precision, batch size, input resolution, pruning, power mode, clock cap and cooling are searched together, every point
          through the same solver. Each recommendation shows what it adds by re-running the recommended setup with that one change
          undone. Other devices and lighter models are checked against the same requirements.
        </p>

        <h2>Learning from your measurements</h2>
        <p>
          Import measurements (a benchmark CSV or JSON, nvidia-smi or tegrastats power logs, or a power meter's CSV) or pair
          your own device and let it time the model. For one device
          and precision, two corrections are fitted: one for achievable efficiency and one for power. A fit is accepted only if it
          predicts measurements it was not fitted on better than the uncorrected model; otherwise it is rejected and the reason is
          shown.
        </p>

        <h2>What is not modelled</h2>
        <ul>
          <li>Heat is one lumped model. The per-component temperatures shown in the thermal view are an attribution of that model, not a separate simulation.</li>
          <li>Accuracy after quantisation, pruning or a lower resolution is a stated prior until you measure it. Model swaps use published accuracy figures.</li>
          <li>No circuit, board, timing or functional simulation. Chip and board suggestions are directional what-ifs.</li>
          <li>Operating-system noise, other workloads sharing the device, and runtime-specific kernel choices are outside the model; measurements capture them.</li>
          <li>Hardware purchase price is not modelled; "running cost" is electricity only.</li>
          <li>A new device entered by hand, or read from a datasheet, is only as good as the figures confirmed for it.</li>
        </ul>
        <p className="hint">The constants behind the model are listed, with their sources, in the project's assumptions document.</p>

        <div className="pub-cta">
          <a className="btn-link primary" href="#/try">See it on an example</a>
          {!signedIn && <a className="btn-link" href="#/signup">Create a free account</a>}
        </div>
      </article>
    </PublicChrome>
  );
}
