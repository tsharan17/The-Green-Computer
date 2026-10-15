import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import AgentPanel from "./components/AgentPanel";
import CodesignTable from "./components/CodesignTable";
import ModelPanel from "./components/ModelPanel";
import ParetoChart from "./components/ParetoChart";
import ThermalChart from "./components/ThermalChart";
import VerifyPanel from "./components/VerifyPanel";
import { Checks, Chip, MetricTable, configLabel, fmt } from "./components/common";
import type {
  Config,
  Constraints,
  EvaluationResult,
  HardwareProfile,
  ModelProfile,
  OptimisationResult,
  ProjectSpec,
  Workload,
} from "./types";

type Tab = "agent" | "setup" | "thermal" | "lab" | "verify";

function Num(props: {
  label: string;
  value: number | null;
  step?: number;
  optional?: boolean;
  onChange: (v: number | null) => void;
}) {
  return (
    <label className="field">
      <span>{props.label}</span>
      <input
        type="number"
        step={props.step ?? 1}
        value={props.value ?? ""}
        placeholder={props.optional ? "none" : ""}
        onChange={(e) => {
          const t = e.target.value;
          props.onChange(t === "" ? (props.optional ? null : 0) : Number(t));
        }}
      />
    </label>
  );
}

function BaselineSummary({ r, title }: { r: EvaluationResult; title: string }) {
  return (
    <section className="panel">
      <div className="row">
        <h2>{title}</h2>
        <Chip state={r.feasibility} />
      </div>
      <p className="hint">
        {configLabel(r.config)} · bottleneck: <strong>{r.bottleneck}</strong> · throttling risk:{" "}
        <strong>{r.throttle_risk}</strong>
      </p>
      <Checks r={r} />
      <MetricTable r={r} />
      {r.notes.map((n) => (
        <p key={n} className="note">{n}</p>
      ))}
    </section>
  );
}

export default function App() {
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [devices, setDevices] = useState<HardwareProfile[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [spec, setSpec] = useState<ProjectSpec | null>(null);
  const [baseline, setBaseline] = useState<EvaluationResult | null>(null);
  const [opt, setOpt] = useState<OptimisationResult | null>(null);
  const [thermalView, setThermalView] = useState<"baseline" | "best">("baseline");
  const [tab, setTab] = useState<Tab>("agent");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [m, d, p] = await Promise.all([api.models(), api.devices(), api.projects()]);
        setModels(m);
        setDevices(d);
        if (p.length) {
          setProjectId(p[0].id);
          setSpec(p[0].spec);
        }
      } catch (e) {
        setError(String(e));
      }
    })();
  }, []);

  const device = useMemo(() => devices.find((d) => d.id === spec?.device_id), [devices, spec]);
  const model = useMemo(() => models.find((m) => m.id === spec?.model_id), [models, spec]);

  if (error && !spec) return <div className="page"><p className="error">Could not reach the API: {error}</p></div>;
  if (!spec || projectId === null) return <div className="page"><p>Loading…</p></div>;

  const setBaselineField = (patch: Partial<Config>) => {
    const d = device;
    if (!d) return;
    const top = [...d.power_modes].sort((a, b) => b.cap_w - a.cap_w)[0];
    const cur: Config = spec.baseline ?? {
      precision: (d.peak_tflops.fp32 ?? 0) > 0 ? "fp32" : "fp16",
      batch: 1,
      power_mode_id: top.id,
      cooling_id: spec.cooling_id ?? d.default_cooling,
      resolution_scale: 1,
      clock_trim: 1,
    };
    const next = { ...cur, ...patch };
    if (!next.power_mode_id) next.power_mode_id = top.id;
    next.cooling_id = spec.cooling_id ?? d.default_cooling;
    setSpec({ ...spec, baseline: next });
  };
  const setWorkload = (patch: Partial<Workload>) => setSpec({ ...spec, workload: { ...spec.workload, ...patch } });
  const setConstraints = (patch: Partial<Constraints>) =>
    setSpec({ ...spec, constraints: { ...spec.constraints, ...patch } });

  async function run(kind: "evaluate" | "optimise") {
    if (!spec || projectId === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.save(projectId, spec);
      if (kind === "evaluate") {
        setBaseline(await api.evaluate(projectId));
        setOpt(null);
        setThermalView("baseline");
      } else {
        const r = await api.optimise(projectId);
        setOpt(r);
        setBaseline(r.baseline);
        setTab("lab");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const thermalResult = thermalView === "best" && opt?.best ? opt.best : baseline;

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>The Green Computer</h1>
          <p className="tag">Predict. Optimise. Verify. Make every computation count.</p>
        </div>
        <span className="pill">Day 4 · Nemotron agent + Nebius GPU jobs</span>
      </header>

      <div className="layout">
        <section className="panel form">
          <h2>Project</h2>
          <label className="field">
            <span>AI model</span>
            <select value={spec.model_id} onChange={(e) => setSpec({ ...spec, model_id: e.target.value })}>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                  {m.fidelity !== "library" ? ` (${m.fidelity})` : ""}
                </option>
              ))}
            </select>
          </label>
          {model && (
            <p className="hint">
              {model.task} · {model.params_m.toFixed(1)} M params · {model.gflops.toFixed(1)} GFLOPs
              {model.fidelity === "library" ? ` · baseline ${model.accuracy_metric} ${(model.baseline_accuracy * 100).toFixed(1)}%` : ""}
            </p>
          )}
          <ModelPanel
            onAdded={(m) => {
              setModels((prev) => [...prev, m]);
              setSpec((s) => (s ? { ...s, model_id: m.id } : s));
            }}
          />
          <label className="field">
            <span>Hardware</span>
            <select
              value={spec.device_id}
              onChange={(e) => {
                const d = devices.find((x) => x.id === e.target.value);
                setSpec({ ...spec, device_id: e.target.value, cooling_id: d?.default_cooling ?? null, baseline: null });
              }}
            >
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          {device && <p className="hint">{device.role}</p>}
          <label className="field">
            <span>Current cooling</span>
            <select value={spec.cooling_id ?? ""} onChange={(e) => setSpec({ ...spec, cooling_id: e.target.value })}>
              {device?.cooling_options.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>

          <details className="model-panel">
            <summary>What you run today (baseline)</summary>
            <p className="hint">Defaults to FP32, batch 1, the highest power mode. Set your real deployment so the comparison is honest.</p>
            {device && (
              <div className="grid2">
                <label className="field"><span>Precision</span>
                  <select
                    value={spec.baseline?.precision ?? ""}
                    onChange={(e) => setBaselineField({ precision: e.target.value as "fp32" | "fp16" | "int8" })}
                  >
                    <option value="">default</option>
                    {(["fp32", "fp16", "int8"] as const).filter((p) => (device.peak_tflops[p] ?? 0) > 0).map((p) => (
                      <option key={p} value={p}>{p.toUpperCase()}</option>
                    ))}
                  </select></label>
                <label className="field"><span>Batch</span>
                  <input type="number" min={1} value={spec.baseline?.batch ?? 1} onChange={(e) => setBaselineField({ batch: Math.max(1, Number(e.target.value) || 1) })} /></label>
                <label className="field"><span>Power mode</span>
                  <select value={spec.baseline?.power_mode_id ?? ""} onChange={(e) => setBaselineField({ power_mode_id: e.target.value })}>
                    <option value="">default (highest)</option>
                    {device.power_modes.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select></label>
                <div className="field"><span>&nbsp;</span>
                  <button onClick={() => setSpec({ ...spec, baseline: null })}>Reset to default</button></div>
              </div>
            )}
          </details>

          <h3>Workload</h3>
          <div className="grid2">
            <Num label="Frames per second" value={spec.workload.fps} onChange={(v) => setWorkload({ fps: v ?? 1 })} />
            <Num label="Ambient °C" value={spec.workload.ambient_c} onChange={(v) => setWorkload({ ambient_c: v ?? 25 })} />
            <Num label="Hours per day" value={spec.workload.hours_per_day} onChange={(v) => setWorkload({ hours_per_day: v ?? 24 })} />
            <Num label="Price per kWh" step={0.01} value={spec.workload.price_per_kwh} onChange={(v) => setWorkload({ price_per_kwh: v ?? 0 })} />
          </div>

          <label className="check-row">
            <input
              type="checkbox"
              checked={spec.workload.streaming}
              onChange={(e) => setWorkload({ streaming: e.target.checked })}
            />
            Real-time stream (a batch waits for its frames)
          </label>

          <h3>Hard constraints</h3>
          <div className="grid2">
            <Num label="Max power (W)" value={spec.constraints.max_power_w} onChange={(v) => setConstraints({ max_power_w: v ?? 55 })} />
            <Num label="Min accuracy (0–1)" step={0.01} value={spec.constraints.min_accuracy} onChange={(v) => setConstraints({ min_accuracy: v ?? 0.9 })} />
            <Num label="Max latency (ms)" optional value={spec.constraints.max_latency_ms} onChange={(v) => setConstraints({ max_latency_ms: v })} />
            <label className="field">
              <span>Accuracy is</span>
              <select
                value={spec.constraints.accuracy_mode}
                onChange={(e) => setConstraints({ accuracy_mode: e.target.value as Constraints["accuracy_mode"] })}
              >
                <option value="relative">% of baseline retained</option>
                <option value="absolute">absolute metric value</option>
              </select>
            </label>
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={spec.constraints.forbid_throttling}
              onChange={(e) => setConstraints({ forbid_throttling: e.target.checked })}
            />
            Reject configurations that throttle
          </label>
          <p className="hint">Constraints are never relaxed automatically.</p>

          <div className="actions">
            <button disabled={busy} onClick={() => run("evaluate")}>
              Evaluate baseline
            </button>
            <button className="primary" disabled={busy} onClick={() => run("optimise")}>
              {busy ? "Working…" : "Find best configuration"}
            </button>
          </div>
          {error && <p className="error">{error}</p>}
        </section>

        <main className="results">
          <nav className="tabs" role="tablist">
            {(
              [
                ["agent", "Agent"],
                ["setup", "Evaluation"],
                ["thermal", "Energy & Thermal"],
                ["lab", "Optimisation Lab"],
                ["verify", "Verify"],
              ] as [Tab, string][]
            ).map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "tab on" : "tab"} onClick={() => setTab(k)}>
                {label}
              </button>
            ))}
          </nav>

          {tab === "agent" && (
            <AgentPanel
              projectId={projectId}
              onProjectChanged={async () => {
                const p = await api.projects();
                const cur = p.find((x) => x.id === projectId);
                if (cur) setSpec(cur.spec);
                setBaseline(null);
                setOpt(null);
              }}
            />
          )}

          {tab === "setup" &&
            (baseline ? (
              <BaselineSummary r={baseline} title="Baseline" />
            ) : (
              <div className="panel empty">Choose a model and hardware, then evaluate the baseline or search for the best configuration.</div>
            ))}

          {tab === "thermal" &&
            (thermalResult ? (
              <section className="panel">
                <div className="row">
                  <h2>Energy &amp; thermal twin</h2>
                  {opt?.best && (
                    <div className="seg">
                      <button className={thermalView === "baseline" ? "on" : ""} onClick={() => setThermalView("baseline")}>Baseline</button>
                      <button className={thermalView === "best" ? "on" : ""} onClick={() => setThermalView("best")}>Recommended</button>
                    </div>
                  )}
                </div>
                <p className="hint">
                  {configLabel(thermalResult.config)} · ambient {fmt(spec.workload.ambient_c)} °C
                </p>
                <ThermalChart r={thermalResult} ambientC={spec.workload.ambient_c} />
                <div className="facts">
                  <div><span>Without governor</span><strong>{fmt(thermalResult.metrics.temperature_unthrottled.value)} °C</strong></div>
                  <div><span>After governor</span><strong>{fmt(thermalResult.metrics.temperature.value)} °C</strong></div>
                  <div><span>Clock factor</span><strong>{(thermalResult.solver.clock_factor * 100).toFixed(0)}%</strong></div>
                  <div><span>Capacity</span><strong>{fmt(thermalResult.metrics.capacity_fps.value)} fps</strong></div>
                  <div><span>Solver</span><strong>{thermalResult.solver.converged ? `converged (${thermalResult.solver.iterations} it)` : "did not converge"}</strong></div>
                </div>
                {thermalResult.notes.map((n) => (
                  <p key={n} className="note">{n}</p>
                ))}
                <p className="hint">
                  Warm-up curve at constant sustained load from a lumped RC model. Power feeds temperature, temperature feeds leakage, and the governor lowers the clock past the throttle point.
                </p>
              </section>
            ) : (
              <div className="panel empty">Run an evaluation first.</div>
            ))}

          {tab === "verify" && (
            <VerifyPanel devices={devices} models={models} onChanged={() => { setOpt(null); setBaseline(null); }} />
          )}

          {tab === "lab" &&
            (opt ? (
              <>
                <section className="panel reco">
                  <div className="row">
                    <h2>Recommendation</h2>
                    {opt.best && <Chip state={opt.best.feasibility} />}
                  </div>
                  {opt.recommendation && opt.best ? (
                    <>
                      <p className="lead">{opt.recommendation.title}</p>
                      <ul className="changes">
                        {opt.recommendation.changes.map((c) => (
                          <li key={c}>{c}</li>
                        ))}
                      </ul>
                      <p>{opt.recommendation.summary}</p>
                      {opt.recommendation.caveats.map((c) => (
                        <p key={c} className="note">{c}</p>
                      ))}
                      <details>
                        <summary>Checks and metrics for the recommended configuration</summary>
                        <p className="hint">{configLabel(opt.best.config)}</p>
                        <Checks r={opt.best} />
                        <MetricTable r={opt.best} />
                      </details>
                    </>
                  ) : (
                    <p className="error">{opt.message}</p>
                  )}
                  <p className="hint">
                    Searched {opt.evaluated} configurations in {opt.search_seconds.toFixed(2)} s:{" "}
                    {Object.entries(opt.counts)
                      .map(([k, v]) => `${v} ${k.replace("_", " ")}`)
                      .join(", ")}
                    .
                  </p>
                </section>

                <section className="panel">
                  <h2>Software vs hardware vs combined</h2>
                  <CodesignTable cd={opt.codesign} />
                </section>

                <section className="panel">
                  <h2>Trade-off frontier</h2>
                  <ParetoChart points={opt.points} baseline={opt.baseline} />
                </section>

                <section className="panel">
                  <h2>{opt.best ? "Top configurations" : "Closest configurations"}</h2>
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>Configuration</th>
                        <th>State</th>
                        <th>Power</th>
                        <th>Energy</th>
                        <th>Latency</th>
                        <th>Temp</th>
                      </tr>
                    </thead>
                    <tbody>
                      {opt.top.map((r, i) => (
                        <tr key={i}>
                          <td>{configLabel(r.config)}</td>
                          <td><Chip state={r.feasibility} /></td>
                          <td>{fmt(r.metrics.power_avg.value)} W</td>
                          <td>{fmt(r.metrics.energy_per_inference.value)} mJ</td>
                          <td>{fmt(r.metrics.latency.value)} ms</td>
                          <td>{fmt(r.metrics.temperature.value)} °C</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              </>
            ) : (
              <div className="panel empty">Run “Find best configuration” to explore the design space.</div>
            ))}
        </main>
      </div>
      <footer className="foot">
        Values are analytical predictions; bands are best/worst-case envelopes, not statistical intervals. Nothing here is measured until a benchmark is linked.
      </footer>
    </div>
  );
}
