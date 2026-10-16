import CustomHardwareWizard from "../components/CustomHardwareWizard";
import DevicePicker from "../components/DevicePicker";
import FileDrop from "../components/FileDrop";
import HardwareImportCard from "../components/HardwareImportCard";
import ModelPanel from "../components/ModelPanel";
import { useState } from "react";
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
  power?: number;
}[] = [
  { title: "Robot that spots objects", blurb: "YOLOv8s on a Jetson Orin NX in a warm room. It overheats today.", model_id: "yolov8s", device_id: "jetson-orin-nx", fps: 30, ambient: 40, latency: 100 },
  { title: "Smart camera", blurb: "MobileNetV2 on a small Jetson Orin Nano. A comfortable fit.", model_id: "mobilenet-v2", device_id: "jetson-orin-nano", fps: 30, ambient: 30, latency: 100 },
  { title: "Fast, heavy vision", blurb: "ResNet-50 at 60 frames/s on a Jetson AGX Orin.", model_id: "resnet-50", device_id: "jetson-agx-orin", fps: 60, ambient: 30, latency: 50 },
  { title: "Camera on a Raspberry Pi", blurb: "MobileNetV2 on a Pi 5 with no fan, in a warm cabinet.", model_id: "mobilenet-v2", device_id: "raspberry-pi-5", fps: 15, ambient: 40, latency: 100, power: 8 },
  { title: "Keyword spotting on a microcontroller", blurb: "A tiny speech model on an STM32H743: does it fit in flash and SRAM?", model_id: "tiny-kws-dscnn", device_id: "stm32h743", fps: 4, ambient: 30, latency: 250, power: 0.5 },
  { title: "Person detection on an FPGA", blurb: "A small vision model on a Kria KV260.", model_id: "tiny-vww-mobilenet", device_id: "xilinx-kria-kv260", fps: 60, ambient: 35, latency: 30, power: 10 },
  { title: "Too much for the board", blurb: "A big detector on the smallest board. See what we suggest.", model_id: "yolov8m", device_id: "jetson-orin-nano", fps: 30, ambient: 40, latency: 100 },
];

function compact(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} billion`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} million`;
  return `${Math.round(n / 1e3)} thousand`;
}

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
  onAnalyse,
  onModelAdded,
  onDevicesChanged,
}: {
  spec: ProjectSpec;
  setSpec: (s: ProjectSpec) => void;
  models: ModelProfile[];
  devices: HardwareProfile[];
  busy: boolean;
  error: string | null;
  onAnalyse: () => void;
  onModelAdded: (m: ModelProfile) => void;
  onDevicesChanged: () => void;
}) {
  const model = models.find((m) => m.id === spec.model_id);
  const device = devices.find((d) => d.id === spec.device_id);
  const [prefill, setPrefill] = useState<{ nonce: number; fields: Record<string, string>; source: string } | null>(null);
  const [draftKey, setDraftKey] = useState(0);
  const setW = (patch: Partial<Workload>) => setSpec({ ...spec, workload: { ...spec.workload, ...patch } });
  const setC = (patch: Partial<Constraints>) => setSpec({ ...spec, constraints: { ...spec.constraints, ...patch } });
  const num = (v: string, fallback: number) => (v === "" ? fallback : Number(v));

  const setBaselineField = (patch: Partial<Config>) => {
    if (!device) return;
    const top = [...device.power_modes].sort((a, b) => b.cap_w - a.cap_w)[0];
    const cur: Config = spec.baseline ?? {
      precision: (["fp32", "fp16", "int8"] as const).find((p) => (device.peak_tflops[p] ?? 0) > 0) ?? "int8",
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
      constraints: { ...spec.constraints, max_latency_ms: p.latency, ...(p.power ? { max_power_w: p.power } : {}) },
    });
  }

  const c = spec.constraints;
  const caveats: string[] = [];
  if (device && !device.verified) caveats.push("Hardware figures are predictions, not measurements.");
  if (model && model.fidelity === "manual") caveats.push("Model entered by hand: wider uncertainty.");

  return (
    <div className="workspace">
      <header className="ws-head">
        <div>
          <span className="eyebrow">Workspace</span>
          <h1>Will your AI run on your hardware?</h1>
          <p className="muted">Upload your model and hardware files, or pick from the library. We predict speed, power and heat, then rank what to change.</p>
        </div>
      </header>

      <FileDrop
        disabled={busy}
        handlers={{
          addModel: onModelAdded,
          applyProject: (sp, hwCreated) => {
            setSpec(sp);
            if (hwCreated) onDevicesChanged();
          },
          hardwareReady: (d) => {
            onDevicesChanged();
            setSpec({ ...spec, device_id: d.id, cooling_id: d.default_cooling ?? null, baseline: null });
          },
          prefill: (fields, source) => setPrefill({ nonce: Date.now(), fields, source }),
          draftsChanged: () => setDraftKey((k) => k + 1),
        }}
      />

      <div className="chips-row" role="group" aria-label="Try an example">
        <span className="muted">No files yet? Try an example:</span>
        {PRESETS.map((p) => (
          <button key={p.title} className="chip-btn" title={p.blurb} onClick={() => applyPreset(p)}>
            {p.title}
          </button>
        ))}
      </div>

      <div className="ws-grid">
        <section className="card" aria-labelledby="sw-h">
          <div className="card-head"><span className="tag-sw">Software</span><h2 id="sw-h">Your AI model</h2></div>
          <select value={spec.model_id} onChange={(e) => setSpec({ ...spec, model_id: e.target.value })} aria-label="AI model">
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}{m.fidelity !== "library" ? " (yours)" : ""}
              </option>
            ))}
          </select>
          {model && (
            <dl className="facts-grid">
              <div><dt>Task</dt><dd>{model.task}</dd></div>
              <div><dt>Parameters</dt><dd>{compact(model.params_m * 1e6)}</dd></div>
              <div><dt>Operations / input</dt><dd>{compact(model.gflops * 1e9)}</dd></div>
              <div><dt>Layers</dt><dd>{model.n_layers}</dd></div>
            </dl>
          )}
          <ModelPanel onAdded={onModelAdded} />
        </section>

        <section className="card" aria-labelledby="hw-h">
          <div className="card-head"><span className="tag-hw">Hardware</span><h2 id="hw-h">Your hardware</h2></div>
          <DevicePicker
            devices={devices}
            value={spec.device_id}
            onPick={(d) => setSpec({ ...spec, device_id: d.id, cooling_id: d.default_cooling ?? null, baseline: null })}
          />
          {device && (
            <dl className="facts-grid">
              <div><dt>Class</dt><dd>{device.kind.replace("_", " ")}</dd></div>
              <div><dt>Compute</dt><dd>{Math.max(...Object.values(device.peak_tflops)).toFixed(1)} T(FL)OPS peak</dd></div>
              <div><dt>Power modes</dt><dd>{device.power_modes.length}</dd></div>
              <div><dt>Evidence</dt><dd>{device.verified ? "measured" : "datasheet / assumed"}</dd></div>
            </dl>
          )}
          {device?.notes && <p className="hint"><small>{device.notes}</small></p>}
          <CustomHardwareWizard
            prefill={prefill}
            onCreated={(d) => {
              onDevicesChanged();
              setSpec({ ...spec, device_id: d.id, cooling_id: d.default_cooling ?? null, baseline: null });
            }}
          />
          <HardwareImportCard onConfirmed={onDevicesChanged} refreshKey={draftKey} />
        </section>
      </div>

      <section className="card" aria-labelledby="rq-h">
        <div className="card-head"><span className="tag-rq">Requirements</span><h2 id="rq-h">What must be true</h2></div>
        <div className="reqs two-col">
          <Row label="Process at least" unit="frames per second" hint={GLOSSARY.fps}>
            <input type="number" value={spec.workload.fps} onChange={(e) => setW({ fps: num(e.target.value, 1) })} />
          </Row>
          <Row label="Use no more than" unit="watts">
            <input type="number" value={c.max_power_w} onChange={(e) => setC({ max_power_w: num(e.target.value, 55) })} />
          </Row>
          <Row label="Keep at least" unit="% of the model's accuracy">
            <input type="number" value={Math.round(c.min_accuracy * 100)} onChange={(e) => setC({ min_accuracy: Math.min(1, Math.max(0.01, num(e.target.value, 90) / 100)) })} />
          </Row>
          <Row label="Answer each frame within" unit="ms (blank = no limit)" hint={GLOSSARY.latency}>
            <input type="number" value={c.max_latency_ms ?? ""} placeholder="none" onChange={(e) => setC({ max_latency_ms: e.target.value === "" ? null : Number(e.target.value) })} />
          </Row>
          <Row label="The room is at" unit="°C">
            <input type="number" value={spec.workload.ambient_c} onChange={(e) => setW({ ambient_c: num(e.target.value, 25) })} />
          </Row>
          <label className="check-row">
            <input type="checkbox" checked={c.forbid_throttling} onChange={(e) => setC({ forbid_throttling: e.target.checked })} />
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
      </section>

      <div className="actionbar" role="region" aria-label="Analyse">
        <div className="ab-summary">
          <strong>{model?.name ?? "-"}</strong> on <strong>{device?.name ?? "-"}</strong>
          <span className="muted"> · {spec.workload.fps} frames/s · ≤ {c.max_power_w} W · ≥ {Math.round(c.min_accuracy * 100)}% accuracy</span>
          {caveats.map((t) => <small key={t} className="ab-caveat">{t}</small>)}
        </div>
        <button className="primary big" disabled={busy} onClick={onAnalyse}>{busy ? "Analysing…" : "Analyse my setup"}</button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
