import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import ErrorBoundary from "./components/ErrorBoundary";
import AgentPanel from "./components/AgentPanel";
import StatusBar from "./components/StatusBar";
import ExplorePage from "./pages/ExplorePage";
import ExportPage from "./pages/ExportPage";
import ResultsPage from "./pages/ResultsPage";
import StartPage from "./pages/StartPage";
import VerifyPage from "./pages/VerifyPage";
import type { HardwareProfile, ModelProfile, OptimisationResult, ProjectSpec } from "./types";

type Page = "start" | "results" | "export" | "explore" | "verify";

export default function App() {
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [devices, setDevices] = useState<HardwareProfile[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [spec, setSpec] = useState<ProjectSpec | null>(null);
  const [res, setRes] = useState<OptimisationResult | null>(null);
  const [page, setPage] = useState<Page>("start");
  const [busy, setBusy] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [m, d, list] = await Promise.all([api.models(), api.devices(), api.projects()]);
        setModels(m);
        setDevices(d);
        // Every visitor gets their own project, remembered in this browser, so people sharing a
        // public demo never overwrite each other's inputs.
        let stored = 0;
        try {
          stored = Number(localStorage.getItem("gc_project_id") || 0);
        } catch {
          /* storage unavailable: fall through to a fresh project */
        }
        let cur = stored ? await api.project(stored).catch(() => null) : null;
        if (!cur) {
          const tpl = list.find((p) => p.spec.name.startsWith("Example")) ?? list[0];
          if (!tpl) throw new Error("No example project is available.");
          cur = await api.create({ ...tpl.spec, name: "My analysis" });
          try {
            localStorage.setItem("gc_project_id", String(cur.id));
          } catch {
            /* ignore */
          }
        }
        setProjectId(cur.id);
        setSpec(cur.spec);
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e));
      }
    })();
  }, []);

  const refreshDevices = useCallback(async () => {
    try {
      const d = await api.devices();
      setDevices(d);
      // A device just added from a datasheet becomes the selected one.
      const custom = d.filter((x) => x.id.startsWith("custom-hw"));
      const newest = custom[custom.length - 1];
      setSpec((s) => (s && newest && !s.device_id.startsWith("custom-hw") ? { ...s, device_id: newest.id, cooling_id: newest.default_cooling, baseline: null } : s));
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    }
  }, []);

  const reloadProject = useCallback(async () => {
    const p = await api.projects();
    const cur = p.find((x) => x.id === projectId);
    if (cur) setSpec(cur.spec);
    setRes(null);
  }, [projectId]);

  async function analyse() {
    if (!spec || projectId === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.save(projectId, spec);
      setRes(await api.optimise(projectId));
      setPage("results");
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  if (error && !spec) {
    return (
      <div className="page">
        <section className="panel" role="alert">
          <h2>We could not load the app</h2>
          <p className="error">{error}</p>
          <button className="primary" onClick={() => window.location.reload()}>Try again</button>
        </section>
      </div>
    );
  }
  if (!spec || projectId === null) {
    return (
      <div className="page">
        <div className="panel skeleton" aria-busy="true" aria-live="polite">
          <div className="sk-line w60" />
          <div className="sk-line w90" />
          <div className="sk-line w75" />
          <p className="hint">Loading The Green Computer…</p>
        </div>
      </div>
    );
  }

  const have = res !== null;
  const nav: { id: Page; n: string; label: string; sub: string; needs?: boolean; on: boolean; icon: string }[] = [
    { id: "start", n: "1", label: "Workspace", sub: "Upload or pick, set requirements", on: page === "start", icon: "⌂" },
    { id: "results", n: "2", label: "Results", sub: "Verdict and ranked changes", needs: true, on: page === "results", icon: "✓" },
    { id: "explore", n: "", label: "Technical details", sub: "Numbers, layers, heat, options", needs: true, on: page === "explore", icon: "≡" },
    { id: "verify", n: "3", label: "Verify", sub: "Real measurements", on: page === "verify", icon: "◎" },
    { id: "export", n: "4", label: "Report and recipe", sub: "Share it, run it", needs: true, on: page === "export", icon: "⇩" },
  ];
  const model = models.find((m) => m.id === spec.model_id);
  const device = devices.find((d) => d.id === spec.device_id);

  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Main">
        <button className="brand" onClick={() => setPage("start")} aria-label="The Green Computer, home">
          <span className="logo" aria-hidden>◐</span>
          <span>
            <strong>The Green Computer</strong>
            <small>Predict. Optimise. Verify.</small>
          </span>
        </button>
        <nav className="side-nav">
          {nav.map((i) => (
            <button key={i.id} className={`nav-item ${i.on ? "on" : ""}`} disabled={i.needs && !have} onClick={() => setPage(i.id)} title={i.needs && !have ? "Analyse your setup first" : undefined}>
              <i aria-hidden>{i.icon}</i>
              <span><strong>{i.label}</strong><small>{i.sub}</small></span>
            </button>
          ))}
        </nav>
        <button className="agent-btn" onClick={() => setAgentOpen(true)}>
          <span aria-hidden>✦</span> Ask the Green Agent
        </button>
        <StatusBar />
      </aside>

      <div className="content">
        <header className="topbar">
          <div>
            <span className="eyebrow">{spec.name}</span>
            <strong>{model?.name ?? "-"}</strong> <span className="muted">on</span> <strong>{device?.name ?? "-"}</strong>
          </div>
          <div className="topbar-right">
            {have && <span className="badge badge-analytical">predicted, not measured</span>}
            {page !== "start" && <button onClick={() => setPage("start")}>Edit inputs</button>}
          </div>
        </header>

        <main>
          <ErrorBoundary>
            {page === "start" && (
              <StartPage
                spec={spec}
                setSpec={setSpec}
                models={models}
                devices={devices}
                busy={busy}
                error={error}
                onAnalyse={analyse}
                onModelAdded={(m) => {
                  setModels((prev) => [...prev.filter((x) => x.id !== m.id), m]);
                  setSpec((s) => (s ? { ...s, model_id: m.id } : s));
                }}
                onDevicesChanged={refreshDevices}
              />
            )}
            {page === "results" && res && <ResultsPage res={res} spec={spec} go={setPage} />}
            {page === "export" && res && <ExportPage projectId={projectId} />}
            {page === "explore" && res && <ExplorePage res={res} spec={spec} projectId={projectId} />}
            {page === "verify" && <VerifyPage devices={devices} models={models} onChanged={() => setRes(null)} />}
          </ErrorBoundary>
        </main>

        <footer className="foot">
          Predictions come from a physics model with stated assumptions; nothing is measured until you add real
          measurements. Your requirements are never relaxed to make a result look good.
        </footer>
      </div>

      {agentOpen && <div className="scrim" onClick={() => setAgentOpen(false)} />}
      <aside className={`drawer ${agentOpen ? "open" : ""}`} aria-hidden={!agentOpen} aria-label="Green Agent">
        <button className="drawer-close" onClick={() => setAgentOpen(false)} aria-label="Close">×</button>
        {agentOpen && <AgentPanel projectId={projectId} onProjectChanged={reloadProject} />}
      </aside>
    </div>
  );
}
