import AgentPanel from "../components/AgentPanel";
import HardwareImportCard from "../components/HardwareImportCard";
import ModelPanel from "../components/ModelPanel";
import { GLOSSARY } from "../lib/plain";
import type { Config, Constraints, HardwareProfile, ModelProfile, ProjectSpec, Workload } from "../types";

const PRESETS: {
  title: string;
  blurb: string;
  model_id: string;
  device_id: string;
  fps: number;
  ambient: number;
  latency: number | null;
}[] = [
  { title: "Robot that spots objects", blurb: "YOLOv8s on a Jetson Orin NX in a warm room. It overheats today.", model_id: "yolov8s", device_id: "jetson-orin-nx", fps: 30, ambient: 40, latency: 100 },
  { title: "Smart camera", blurb: "MobileNetV2 on a small Jetson Orin Nano. A comfortable fit.", model_id: "mobilenet-v2", device_id: "jetson-orin-nano", fps: 30, ambient: 30, latency: 100 },
  { title: "Fast, heavy vision", blurb: "ResNet-50 at 60 frames/s on a Jetson AGX Orin.", model_id: "resnet-50", device_id: "jetson-agx-orin", fps: 60, ambient: 30, latency: 50 },
  { title: "Too much for the board", blurb: "A big detector on the smallest board. See what we suggest.", model_id: "yolov8m", device_id: "jetson-orin-nano", fps: 30, ambient: 40, latency: 100 },
];

function Row({
  children,
  unit,
  label,
  hint,
}: {
  children: React.ReactNode;
  unit: string;
  label: string;
  hint?: string;
}) {
  return (
    <label className="req-row">
      <span className="req-label">
        {label}
        {hint && <small title={hint}> ⓘ</small>}
      </span>
      <span className="req-input">
        {children}
        <em>{unit}</em>
      </span>
    </label>
  );
}

export default function StartPage({
  spec,
  setSpec,
  models,
  devices,
  busy,
  error,
  projectId,
  onAnalyse,
  onModelAdded,
  onDevicesChanged,
  onProjectChanged,
}: {
  spec: ProjectSpec;
  setSpec: (s: ProjectSpec) => void;
  models: ModelProfile[];
  devices: HardwareProfile[];
  busy: boolean;
  error: string | null;
  projectId: number;
  onAnalyse: () => void;
  onModelAdded: (m: ModelProfile) => void;
  onDevicesChanged: () => void;
  onProjectChanged: () => void;
}) {
  const model = models.find((m) => m.id === spec.model_id);
  const device = devices.find((d) => d.id === spec.device_id);
  const setW = (patch: Partial<Workload>) => setSpec({ ...spec, workload: { ...spec.workload, ...patch } });
  const setC = (patch: Partial<Constraints>) => setSpec({ ...spec, constraints: { ...spec.constraints, ...patch } });
  const num = (v: string, fallback: number) => (v === "" ? fallback : Number(v));

  const setBaselineField = (patch: Partial<Config>) => {
    if (!device) return;
    const top = [...device.power_modes].sort((a, b) => b.cap_w - a.cap_w)[0];
    const cur: Config = spec.baseline ?? {
      precision: (device.peak_tflops.fp32 ?? 0) > 0 ? "fp32" : "fp16",
      batch: 1,
      power_mode_id: top.id,
      cooling_id: spec.cooling_id ?? device.default_cooling,
      resolution_scale: 1,
      clock_trim: 1,
      sparsity: 0,
    };
    const next = { ...cur, ...patch };
    if (!next.power_mode_id) next.power_mode_id = top.id;
    next.cooling_id = spec.cooling_id ?? device.default_cooling;
    setSpec({ ...spec, baseline: next });
  };

  function applyPreset(p: (typeof PRESETS)[number]) {
    const d = devices.find((x) => x.id === p.device_id);
    setSpec({
      ...spec,
      model_id: p.model_id,
      device_id: p.device_id,
      cooling_id: d?.default_cooling ?? null,
      baseline: null,
      workload: { ...spec.workload, fps: p.fps, ambient_c: p.ambient },
      constraints: { ...spec.constraints, max_latency_ms: p.latency },
    });
  }

  return (
    <div className="start">
      <section className="hero">
        <h1>Will your AI run on your hardware, and how do you make it greener?</h1>
        <p>
          Tell us the AI model, the hardware and what must be true. We predict how it will behave <em>before you build
          anything</em>, then show exactly what to change, from the AI model to the chip, to hit your targets on the least
          energy.
        </p>
        <div className="how">
          <div><b>1</b><strong>Predict</strong><span>See speed, power and heat for your setup, with a range, not a guess.</span></div>
          <div><b>2</b><strong>Optimise</strong><span>Get ranked changes to the model, the settings, the hardware and the design.</span></div>
          <div><b>3</b><strong>Verify</strong><span>Add real measurements so the predictions get more accurate.</span></div>
        </div>
      </section>

      <div className="start-grid">
        <div>
          <section className="panel">
            <h2>Try an example</h2>
            <div className="presets">
              {PRESETS.map((p) => (
                <button key={p.title} className="preset" onClick={() => applyPreset(p)}>
                  <strong>{p.title}</strong>
                  <span>{p.blurb}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="panel form">
            <h2>1 · What AI are you running?</h2>
            <label className="field">
              <select value={spec.model_id} onChange={(e) => setSpec({ ...spec, model_id: e.target.value })} aria-label="AI model">
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}{m.fidelity !== "library" ? ` (yours)` : ""}
                  </option>
                ))}
              </select>
            </label>
            {model && (
              <p className="hint">
                {model.task} · {model.params_m.toFixed(1)} million parameters · {model.gflops.toFixed(1)} billion operations per image
              </p>
            )}
            <ModelPanel onAdded={onModelAdded} />

            <h2>2 · What hardware?</h2>
            <label className="field">
              <select value={spec.device_id} onChange={(e) => {
                const d = devices.find((x) => x.id === e.target.value);
                setSpec({ ...spec, device_id: e.target.value, cooling_id: d?.default_cooling ?? null, baseline: null });
              }} aria-label="Hardware">
                {devices.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </label>
            {device && <p className="hint">{device.role}</p>}
            <HardwareImportCard onConfirmed={onDevicesChanged} />

            <h2>3 · What must be true?</h2>
            <div className="reqs">
              <Row label="Process at least" unit="frames per second" hint={GLOSSARY.fps}>
                <input type="number" value={spec.workload.fps} onChange={(e) => setW({ fps: num(e.target.value, 1) })} />
              </Row>
              <Row label="Use no more than" unit="watts">
                <input type="number" value={spec.constraints.max_power_w} onChange={(e) => setC({ max_power_w: num(e.target.value, 55) })} />
              </Row>
              <Row label="Keep at least" unit="% of the model's accuracy">
                <input type="number" value={Math.round(spec.constraints.min_accuracy * 100)} onChange={(e) => setC({ min_accuracy: Math.min(1, Math.max(0.01, num(e.target.value, 90) / 100)) })} />
              </Row>
              <Row label="Answer each frame within" unit="milliseconds (blank = no limit)" hint={GLOSSARY.latency}>
                <input type="number" value={spec.constraints.max_latency_ms ?? ""} placeholder="none" onChange={(e) => setC({ max_latency_ms: e.target.value === "" ? null : Number(e.target.value) })} />
              </Row>
              <Row label="The room is at" unit="°C">
                <input type="number" value={spec.workload.ambient_c} onChange={(e) => setW({ ambient_c: num(e.target.value, 25) })} />
              </Row>
              <label className="check-row">
                <input type="checkbox" checked={spec.constraints.forbid_throttling} onChange={(e) => setC({ forbid_throttling: e.target.checked })} />
                <span>Don't let it overheat and slow itself down <small title={GLOSSARY.throttle}>ⓘ</small></span>
              </label>
            </div>
            <p className="hint">We never loosen these to make a result look better.</p>

            <details className="adv">
              <summary>More settings (optional)</summary>
              <div className="grid2">
                <label className="field"><span>Hours it runs per day</span><input type="number" value={spec.workload.hours_per_day} onChange={(e) => setW({ hours_per_day: num(e.target.value, 24) })} /></label>
                <label className="field"><span>Electricity price per kWh</span><input type="number" step={0.01} value={spec.workload.price_per_kwh} onChange={(e) => setW({ price_per_kwh: num(e.target.value, 0.15) })} /></label>
                <label className="field"><span>Current cooling</span>
                  <select value={spec.cooling_id ?? ""} onChange={(e) => setSpec({ ...spec, cooling_id: e.target.value })}>
                    {device?.cooling_options.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select></label>
                <label className="field"><span>Accuracy means</span>
                  <select value={spec.constraints.accuracy_mode} onChange={(e) => setC({ accuracy_mode: e.target.value as Constraints["accuracy_mode"] })}>
                    <option value="relative">% of the model's own accuracy</option>
                    <option value="absolute">absolute score (such as mAP)</option>
                  </select></label>
              </div>
              <label className="check-row">
                <input type="checkbox" checked={spec.workload.streaming} onChange={(e) => setW({ streaming: e.target.checked })} />
                <span>Frames arrive live, one at a time (batching makes each wait) <small title={GLOSSARY.batch}>ⓘ</small></span>
              </label>
              <h3>What you run today</h3>
              <p className="hint">Leave empty to compare against the plain default (full precision, no batching, top power mode).</p>
              {device && (
                <div className="grid2">
                  <label className="field"><span>Number format</span>
                    <select value={spec.baseline?.precision ?? ""} onChange={(e) => e.target.value ? setBaselineField({ precision: e.target.value as "fp32" | "fp16" | "int8" }) : setSpec({ ...spec, baseline: null })}>
                      <option value="">default</option>
                      {(["fp32", "fp16", "int8"] as const).filter((p) => (device.peak_tflops[p] ?? 0) > 0).map((p) => (
                        <option key={p} value={p}>{p.toUpperCase()}</option>
                      ))}
                    </select></label>
                  <label className="field"><span>Frames per batch</span>
                    <input type="number" min={1} value={spec.baseline?.batch ?? 1} onChange={(e) => setBaselineField({ batch: Math.max(1, Number(e.target.value) || 1) })} /></label>
                  <label className="field"><span>Power mode</span>
                    <select value={spec.baseline?.power_mode_id ?? ""} onChange={(e) => setBaselineField({ power_mode_id: e.target.value })}>
                      <option value="">default (highest)</option>
                      {device.power_modes.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                    </select></label>
                </div>
              )}
            </details>

            <button className="primary big" disabled={busy} onClick={onAnalyse}>
              {busy ? "Analysing…" : "Analyse my setup"}
            </button>
            <p className="hint center">Takes a couple of seconds. Nothing is installed or run on your hardware.</p>
            {error && <p className="error">{error}</p>}
          </section>
        </div>

        <div className="start-side">
          <AgentPanel projectId={projectId} onProjectChanged={onProjectChanged} />
        </div>
      </div>
    </div>
  );
}
