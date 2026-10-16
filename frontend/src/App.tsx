import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import ErrorBoundary from "./components/ErrorBoundary";
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
  const steps: { id: Page; n: string; label: string; needs?: boolean }[] = [
    { id: "start", n: "1", label: "Describe" },
    { id: "results", n: "2", label: "Results", needs: true },
    { id: "export", n: "3", label: "Export", needs: true },
  ];

  return (
    <div className="page">
      <header className="top">
        <button className="brand" onClick={() => setPage("start")} aria-label="The Green Computer, home">
          <span className="logo" aria-hidden>◐</span>
          <span>
            <strong>The Green Computer</strong>
            <small>Predict. Optimise. Verify. Make every computation count.</small>
          </span>
        </button>
        <nav className="steps" aria-label="Steps">
          {steps.map((s) => (
            <button key={s.id} className={`step-btn ${page === s.id ? "on" : ""}`} disabled={s.needs && !have} onClick={() => setPage(s.id)} title={s.needs && !have ? "Analyse your setup first" : undefined}>
              <b>{s.n}</b> {s.label}
            </button>
          ))}
          <span className="sep" aria-hidden />
          <button className={`step-btn minor ${page === "explore" ? "on" : ""}`} disabled={!have} onClick={() => setPage("explore")}>
            Technical details
          </button>
          <button className={`step-btn minor ${page === "verify" ? "on" : ""}`} onClick={() => setPage("verify")}>
            Real measurements
          </button>
        </nav>
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
            projectId={projectId}
            onAnalyse={analyse}
            onModelAdded={(m) => {
              setModels((prev) => [...prev, m]);
              setSpec((s) => (s ? { ...s, model_id: m.id } : s));
            }}
            onDevicesChanged={refreshDevices}
            onProjectChanged={reloadProject}
          />
        )}
        {page === "results" && res && <ResultsPage res={res} spec={spec} go={setPage} />}
        {page === "export" && res && <ExportPage projectId={projectId} />}
        {page === "explore" && res && <ExplorePage res={res} spec={spec} projectId={projectId} />}
        {page === "verify" && (
          <VerifyPage devices={devices} models={models} onChanged={() => setRes(null)} />
        )}
        </ErrorBoundary>
      </main>

      <footer className="foot">
        Predictions come from a physics model with stated assumptions; nothing is measured until you add real
        measurements. Your requirements are never relaxed to make a result look good.
      </footer>
    </div>
  );
}
