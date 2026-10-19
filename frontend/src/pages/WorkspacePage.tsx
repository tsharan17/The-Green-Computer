import { useCallback, useEffect, useState } from "react";
import { api, history, workspace } from "../api";
import { navigate } from "../router";
import type { HardwareProfile, Me, ModelProfile, ProjectOut, ProjectSpec, UsageSummary } from "../types";

const STEPS = [
  ["Describe the system", "Upload an ONNX model and a hardware profile, or pick from the library."],
  ["Set what must be true", "Frame rate, power and latency limits, accuracy, room temperature."],
  ["Analyse", "Predicted execution trace, memory, heat and energy, each with its range and source."],
  ["Decide", "Select recommendations into a plan, re-analyse and compare old with new."],
  ["Verify and hand over", "Run it locally or import measurements, calibrate, export the plan."],
];

function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function when(iso: string | null | undefined) {
  if (!iso) return "–";
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function WorkspacePage({
  me,
  models,
  devices,
}: {
  me: Me;
  models: ModelProfile[];
  devices: HardwareProfile[];
}) {
  const [projects, setProjects] = useState<ProjectOut[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [from, setFrom] = useState<string>("example");
  const [busy, setBusy] = useState(false);
  const ws = me.workspaces.find((w) => w.id === me.active_workspace_id);
  const canWrite = me.role === "owner" || me.role === "editor";

  const load = useCallback(async () => {
    try {
      const [p, u] = await Promise.all([history.projects(showArchived), workspace.usage()]);
      setProjects(p);
      setUsage(u);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [showArchived]);
  useEffect(() => {
    load();
  }, [load]);

  const label = (s: ProjectSpec) =>
    `${models.find((m) => m.id === s.model_id)?.name ?? s.model_id} on ${devices.find((d) => d.id === s.device_id)?.name ?? s.device_id}`;

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!projects) return;
    setBusy(true);
    setError(null);
    try {
      let spec: ProjectSpec;
      const src = projects.find((p) => String(p.id) === from);
      if (src) spec = { ...src.spec };
      else {
        const dev = devices.find((d) => d.id === "jetson-orin-nano") ?? devices[0];
        spec = {
          name: "",
          model_id: from === "example" ? "yolov8s" : models[0]?.id ?? "resnet-50",
          device_id: from === "example" ? "jetson-orin-nx" : dev.id,
          cooling_id: from === "example" ? "passive_small" : dev.default_cooling,
          baseline: null,
          workload: { fps: 30, ambient_c: 40, hours_per_day: 24, price_per_kwh: 0.15, grid_gco2_per_kwh: 400, streaming: true },
          constraints: { max_power_w: 55, min_accuracy: 0.9, accuracy_mode: "relative", max_latency_ms: null, max_memory_gb: null, forbid_throttling: true },
        } as ProjectSpec;
      }
      spec.name = name.trim() || "Untitled project";
      const p = await api.create(spec);
      navigate(`/p/${p.id}/input`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleArchive(p: ProjectOut) {
    try {
      await history.archive(p.id, !p.archived);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const first = projects !== null && projects.length <= 1;
  return (
    <div className="workspace">
      <header className="ws-head">
        <h1>{first ? `Welcome${me.user.display_name ? `, ${me.user.display_name}` : ""}` : ws?.name ?? "Workspace"}</h1>
        <p className="muted">
          {first
            ? "Start with the example project to see a full analysis in a minute, or create your own from an uploaded model."
            : "Your projects. Each change of inputs is kept as a version; every analysis and export is in the project history."}
        </p>
      </header>

      {first && (
        <ol className="how-steps" aria-label="How it works">
          {STEPS.map(([t, d]) => (
            <li key={t}>
              <strong>{t}</strong>
              <span>{d}</span>
            </li>
          ))}
        </ol>
      )}

      {error && <p className="error" role="alert">{error}</p>}

      <section className="panel" aria-labelledby="proj-h">
        <div className="row">
          <h2 id="proj-h">Projects</h2>
          <label className="check-row">
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Show archived
          </label>
        </div>
        {projects === null ? (
          <div className="skeleton" aria-busy="true"><div className="sk-line w90" /><div className="sk-line w75" /></div>
        ) : projects.length === 0 ? (
          <p className="empty">No projects yet. Create one below; it starts from the example inputs so you can analyse straight away.</p>
        ) : (
          <div className="table-wrap">
            <table className="tbl projects">
              <thead>
                <tr><th>Project</th><th>System</th><th>Version</th><th>Last change</th><th><span className="sr-only">Actions</span></th></tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id} className={p.archived ? "archived" : ""}>
                    <td><a href={`#/p/${p.id}/input`}>{p.spec.name}</a>{p.archived && <span className="badge"> archived</span>}</td>
                    <td className="muted">{label(p.spec)}</td>
                    <td className="num">v{p.version}</td>
                    <td className="muted">{when(p.updated_at)}</td>
                    <td className="actions-cell">
                      <a className="btn-link" href={`#/p/${p.id}/recommendations`}>Results</a>
                      {canWrite && <button className="link" onClick={() => toggleArchive(p)}>{p.archived ? "Restore" : "Archive"}</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="ws-grid">
        {canWrite && (
          <section className="panel" aria-labelledby="new-h">
            <h2 id="new-h">New project</h2>
            <form onSubmit={create}>
              <label className="field">
                Name
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Pick-and-place vision on Orin NX" maxLength={200} />
              </label>
              <label className="field">
                Start from
                <select value={from} onChange={(e) => setFrom(e.target.value)}>
                  <option value="example">The robotics example (YOLOv8s, 30 FPS, 55 W, 40 °C)</option>
                  <option value="blank">Library defaults (you choose model and hardware next)</option>
                  {(projects ?? []).filter((p) => !p.archived).map((p) => (
                    <option key={p.id} value={String(p.id)}>A copy of “{p.spec.name}”</option>
                  ))}
                </select>
              </label>
              <button className="primary" disabled={busy || projects === null}>{busy ? "Creating…" : "Create project"}</button>
            </form>
          </section>
        )}

        <section className="panel" aria-labelledby="use-h">
          <h2 id="use-h">Usage this month</h2>
          {usage ? (
            <>
              <dl className="kv">
                <dt>Analyses</dt><dd className="num">{usage.this_period.analysis + usage.this_period.plan_analysis}</dd>
                <dt>Local execution</dt><dd className="num">{(usage.this_period.execution_seconds / 60).toFixed(1)} min</dd>
                <dt>Remote GPU</dt><dd className="num">{(usage.this_period.remote_gpu_seconds / 60).toFixed(1)} min</dd>
                <dt>Exports</dt><dd className="num">{usage.this_period.export}</dd>
                <dt>Files stored</dt><dd className="num">{fmtBytes(usage.storage_bytes_in_use)}</dd>
                <dt>Platform cost</dt>
                <dd className="num">{usage.platform_cost.total.toFixed(2)} {usage.platform_cost.currency}</dd>
              </dl>
              <p className="hint">{usage.platform_cost.note} {usage.device_energy_note}</p>
            </>
          ) : (
            <div className="skeleton" aria-busy="true"><div className="sk-line w60" /></div>
          )}
        </section>
      </div>
    </div>
  );
}
