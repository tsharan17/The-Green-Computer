import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type {
  Constraints,
  EvaluationResult,
  Feasibility,
  HardwareProfile,
  Metric,
  ModelProfile,
  OptimisationResult,
  ProjectSpec,
  Workload,
} from "./types";

const STATE_LABEL: Record<Feasibility, string> = {
  verified_feasible: "Verified feasible",
  predicted_feasible: "Predicted feasible",
  uncertain: "Uncertain",
  infeasible: "Infeasible",
  verified_infeasible: "Verified infeasible",
};

const METRIC_ROWS: [string, string][] = [
  ["latency", "Latency (per batch)"],
  ["capacity_fps", "Throughput capacity"],
  ["power_avg", "Average power"],
  ["power_peak", "Peak power"],
  ["energy_per_inference", "Energy per inference"],
  ["temperature", "Steady temperature"],
  ["thermal_headroom", "Thermal headroom"],
  ["memory", "Memory"],
  ["accuracy", "Accuracy"],
  ["cost_per_day", "Electricity cost"],
  ["carbon_per_day", "Carbon"],
];

function fmt(n: number): string {
  const a = Math.abs(n);
  if (a >= 100) return n.toFixed(0);
  if (a >= 10) return n.toFixed(1);
  return n.toFixed(2);
}

function Chip({ state }: { state: Feasibility }) {
  return <span className={`chip chip-${state}`}>{STATE_LABEL[state]}</span>;
}

function Badge({ p }: { p: Metric["provenance"] }) {
  return <span className={`badge badge-${p}`}>{p.replace("_", " ")}</span>;
}

function MetricTable({ r }: { r: EvaluationResult }) {
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>Metric</th>
          <th>Value</th>
          <th>Band (low – high)</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {METRIC_ROWS.map(([k, label]) => {
          const m = r.metrics[k];
          if (!m) return null;
          return (
            <tr key={k}>
              <td>{label}</td>
              <td>
                <strong>{fmt(m.value)}</strong> {m.unit}
              </td>
              <td className="muted">
                {fmt(m.low)} – {fmt(m.high)}
              </td>
              <td>
                <Badge p={m.provenance} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Checks({ r }: { r: EvaluationResult }) {
  return (
    <ul className="checks">
      {r.checks.map((c) => (
        <li key={c.name} className={`check check-${c.status}`}>
          <span className="check-dot" />
          <span>
            <strong>{c.name}</strong> {c.sense} {fmt(c.limit)} {c.unit}
            <span className="muted">
              {" "}
              — worst case {fmt(c.pessimistic)}, best case {fmt(c.optimistic)}
              {c.note ? ` (${c.note})` : ""}
            </span>
          </span>
          <span className="check-status">{c.status}</span>
        </li>
      ))}
    </ul>
  );
}

function configLabel(r: EvaluationResult): string {
  const c = r.config;
  return `${c.precision.toUpperCase()} · batch ${c.batch} · ${c.power_mode_id} · ${c.cooling_id}`;
}

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

export default function App() {
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [devices, setDevices] = useState<HardwareProfile[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [spec, setSpec] = useState<ProjectSpec | null>(null);
  const [baseline, setBaseline] = useState<EvaluationResult | null>(null);
  const [opt, setOpt] = useState<OptimisationResult | null>(null);
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
      } else {
        const r = await api.optimise(projectId);
        setOpt(r);
        setBaseline(r.baseline);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const shown = baseline;

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>The Green Computer</h1>
          <p className="tag">Predict. Optimise. Verify. Make every computation count.</p>
        </div>
        <span className="pill">Day 1 · analytical L0 simulator</span>
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
                </option>
              ))}
            </select>
          </label>
          {model && (
            <p className="hint">
              {model.task} · baseline {model.accuracy_metric} {(model.baseline_accuracy * 100).toFixed(1)}%
            </p>
          )}
          <label className="field">
            <span>Hardware</span>
            <select
              value={spec.device_id}
              onChange={(e) => {
                const d = devices.find((x) => x.id === e.target.value);
                setSpec({ ...spec, device_id: e.target.value, cooling_id: d?.default_cooling ?? null });
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

          <h3>Workload</h3>
          <div className="grid2">
            <Num label="Frames per second" value={spec.workload.fps} onChange={(v) => setWorkload({ fps: v ?? 1 })} />
            <Num label="Ambient °C" value={spec.workload.ambient_c} onChange={(v) => setWorkload({ ambient_c: v ?? 25 })} />
            <Num label="Hours per day" value={spec.workload.hours_per_day} onChange={(v) => setWorkload({ hours_per_day: v ?? 24 })} />
            <Num label="Price per kWh" step={0.01} value={spec.workload.price_per_kwh} onChange={(v) => setWorkload({ price_per_kwh: v ?? 0 })} />
          </div>

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
          {!shown && <div className="panel empty">Choose a model and hardware, then evaluate the baseline or search for the best configuration.</div>}

          {shown && (
            <section className="panel">
              <div className="row">
                <h2>Baseline</h2>
                <Chip state={shown.feasibility} />
              </div>
              <p className="hint">
                {configLabel(shown)} · bottleneck: <strong>{shown.bottleneck}</strong> · throttling risk:{" "}
                <strong>{shown.throttle_risk}</strong>
              </p>
              <Checks r={shown} />
              <MetricTable r={shown} />
              {shown.notes.map((n) => (
                <p key={n} className="note">{n}</p>
              ))}
            </section>
          )}

          {opt && (
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
                      <p className="hint">{configLabel(opt.best)}</p>
                      <Checks r={opt.best} />
                      <MetricTable r={opt.best} />
                    </details>
                  </>
                ) : (
                  <p className="error">{opt.message}</p>
                )}
                <p className="hint">
                  Searched {opt.evaluated} configurations:{" "}
                  {Object.entries(opt.counts)
                    .map(([k, v]) => `${v} ${k.replace("_", " ")}`)
                    .join(", ")}
                  .
                </p>
              </section>

              <section className="panel">
                <h2>{opt.best ? "Top configurations (lowest energy first)" : "Closest configurations"}</h2>
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
                        <td>{configLabel(r)}</td>
                        <td>
                          <Chip state={r.feasibility} />
                        </td>
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
          )}
        </main>
      </div>
      <footer className="foot">
        Values are L0 analytical predictions with stated uncertainty. Nothing here is measured until a benchmark is linked.
      </footer>
    </div>
  );
}
