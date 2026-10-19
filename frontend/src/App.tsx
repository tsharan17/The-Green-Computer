import Logo from "./components/Logo";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, auth, history, setWorkspace } from "./api";
import AgentPanel from "./components/AgentPanel";
import ErrorBoundary from "./components/ErrorBoundary";
import ExecutionPanel from "./components/ExecutionPanel";
import ExportPanel from "./components/ExportPanel";
import HistoryPanel from "./components/HistoryPanel";
import PlanBuilder from "./components/PlanBuilder";
import SavedPlans from "./components/SavedPlans";
import StatusBar from "./components/StatusBar";
import AccountPage from "./pages/AccountPage";
import AuthPage from "./pages/AuthPage";
import ResultsPage from "./pages/ResultsPage";
import CapabilitiesPage from "./pages/CapabilitiesPage";
import ConstraintsPage from "./pages/ConstraintsPage";
import InputPage from "./pages/InputPage";
import VerifyPage from "./pages/VerifyPage";
import WorkspacePage from "./pages/WorkspacePage";
import { AREAS, type AreaId, navigate, useRoute } from "./router";
import MemoryPage from "./twin/MemoryPage";
import SystemMapPage from "./twin/SystemMapPage";
import { EnergyPage, ThermalPage } from "./twin/ThermalEnergyPages";
import TimelinePage from "./twin/TimelinePage";
import type { HardwareProfile, Me, ModelProfile, OptimisationResult, ProjectOut, ProjectSpec } from "./types";

const WS_KEY = "gc_workspace";

function readWs(): number | null {
  try {
    return Number(localStorage.getItem(WS_KEY)) || null;
  } catch {
    return null;
  }
}

function msg(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}

export default function App() {
  const route = useRoute();
  const [me, setMe] = useState<Me | null | undefined>(undefined);

  const loadMe = useCallback(async () => {
    try {
      const m = await auth.me();
      const stored = readWs();
      const active = m.workspaces.find((w) => w.id === stored) ? stored : m.active_workspace_id;
      setWorkspace(active);
      setMe({ ...m, active_workspace_id: active, role: m.workspaces.find((w) => w.id === active)?.role ?? null });
    } catch {
      setWorkspace(null);
      setMe(null);
    }
  }, []);

  useEffect(() => {
    loadMe();
    const out = () => setMe(null);
    window.addEventListener("gc:unauthorized", out);
    return () => window.removeEventListener("gc:unauthorized", out);
  }, [loadMe]);

  const page = route.parts[0] ?? "";
  if (page === "reset") return <AuthPage mode="reset" token={route.query.get("token") ?? ""} onSignedIn={() => loadMe()} />;
  if (me === undefined) {
    return (
      <div className="boot" aria-busy="true" aria-live="polite">
        <Logo /> Loading The Green Computer…
      </div>
    );
  }
  if (me === null) {
    const mode = page === "signup" || page === "forgot" ? page : "signin";
    return (
      <AuthPage
        mode={mode}
        onSignedIn={(m) => {
          setWorkspace(m.active_workspace_id);
          setMe(m);
          navigate("/");
        }}
      />
    );
  }
  return (
    <Shell
      me={me}
      route={route}
      switchWorkspace={(id) => {
        try {
          localStorage.setItem(WS_KEY, String(id));
        } catch {
          /* storage unavailable: the choice lasts for this tab only */
        }
        setWorkspace(id);
        setMe({ ...me, active_workspace_id: id, role: me.workspaces.find((w) => w.id === id)?.role ?? null });
        navigate("/");
      }}
      reloadMe={loadMe}
      signedOut={() => {
        setWorkspace(null);
        setMe(null);
        navigate("/signin");
      }}
    />
  );
}

function Shell({
  me,
  route,
  switchWorkspace,
  reloadMe,
  signedOut,
}: {
  me: Me;
  route: ReturnType<typeof useRoute>;
  switchWorkspace: (id: number) => void;
  reloadMe: () => void;
  signedOut: () => void;
}) {
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [devices, setDevices] = useState<HardwareProfile[]>([]);
  const [libError, setLibError] = useState<string | null>(null);
  const [agentOpen, setAgentOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const refreshLibrary = useCallback(async () => {
    try {
      const [m, d] = await Promise.all([api.models(), api.devices()]);
      setModels(m);
      setDevices(d);
      setLibError(null);
    } catch (e) {
      setLibError(msg(e));
    }
  }, []);
  useEffect(() => {
    refreshLibrary();
  }, [refreshLibrary, me.active_workspace_id]);

  const [p0, p1, p2] = route.parts;
  const projectId = p0 === "p" && p1 ? Number(p1) : null;
  const area = (AREAS.some((a) => a.id === p2) ? p2 : "input") as AreaId;
  const canWrite = me.role === "owner" || me.role === "editor";

  async function signOut() {
    try {
      await auth.signout();
    } finally {
      signedOut();
    }
  }

  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <aside className="sidebar" aria-label="Main navigation">
        <a className="brand" href="#/" aria-label="The Green Computer, workspace">
          <Logo />
          <span>
            <strong>The Green Computer</strong>
            <small>AI and hardware co-design</small>
          </span>
        </a>
        <nav className="side-nav">
          <a className={`nav-item ${!projectId && !p0 ? "on" : ""}`} href="#/" aria-current={!projectId && !p0 ? "page" : undefined}>
            <i aria-hidden>1</i>
            <span><strong>Workspace</strong><small>Projects and onboarding</small></span>
          </a>
          {projectId !== null &&
            AREAS.filter((a) => BUILT.has(a.id)).map((a) => (
              <a key={a.id} className={`nav-item ${area === a.id ? "on" : ""}`} href={`#/p/${projectId}/${a.id}`} aria-current={area === a.id ? "page" : undefined}>
                <i aria-hidden>{a.n}</i>
                <span><strong>{a.label}</strong><small>{a.sub}</small></span>
              </a>
            ))}
        </nav>
        {projectId !== null && (
          <button className="agent-btn" onClick={() => setAgentOpen(true)}>
            Ask the assistant
          </button>
        )}
        <a className={`cap-link ${p0 === "capabilities" ? "on" : ""}`} href="#/capabilities">What this installation can do</a>
        <StatusBar />
      </aside>

      <div className="content">
        <header className="topbar">
          <label className="ws-switch">
            <span className="sr-only">Workspace</span>
            <select value={me.active_workspace_id ?? ""} onChange={(e) => switchWorkspace(Number(e.target.value))}>
              {me.workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}{w.role !== "owner" ? ` (${w.role})` : ""}
                </option>
              ))}
            </select>
          </label>
          <div className="account-menu">
            <button aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}>
              {me.user.display_name || me.user.email}
            </button>
            {menuOpen && (
              <div className="menu" role="menu" onClick={() => setMenuOpen(false)}>
                <a role="menuitem" href="#/account">Account and workspace</a>
                <button role="menuitem" onClick={signOut}>Sign out</button>
              </div>
            )}
          </div>
        </header>

        <main id="main" tabIndex={-1}>
          {libError && <p className="error" role="alert">{libError}</p>}
          <ErrorBoundary>
            {p0 === "account" ? (
              <AccountPage me={me} onChanged={reloadMe} onDeleted={signedOut} />
            ) : p0 === "capabilities" ? (
              <CapabilitiesPage />
            ) : projectId !== null ? (
              <ProjectView
                key={`${me.active_workspace_id}-${projectId}`}
                projectId={projectId}
                area={area}
                query={route.query}
                models={models}
                devices={devices}
                canWrite={canWrite}
                setModels={setModels}
                refreshLibrary={refreshLibrary}
                agentOpen={agentOpen}
                closeAgent={() => setAgentOpen(false)}
              />
            ) : (
              <WorkspacePage me={me} models={models} devices={devices} />
            )}
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}

/** Areas that have a screen in this build (others are hidden, never shown as dead links). */
const BUILT = new Set<AreaId>(["input", "constraints", "system-map", "timeline", "memory", "thermal", "energy", "recommendations", "verify"]);

function ProjectView({
  projectId,
  area,
  query,
  models,
  devices,
  canWrite,
  setModels,
  refreshLibrary,
  agentOpen,
  closeAgent,
}: {
  projectId: number;
  area: AreaId;
  query: URLSearchParams;
  models: ModelProfile[];
  devices: HardwareProfile[];
  canWrite: boolean;
  setModels: React.Dispatch<React.SetStateAction<ModelProfile[]>>;
  refreshLibrary: () => Promise<void>;
  agentOpen: boolean;
  closeAgent: () => void;
}) {
  const [project, setProject] = useState<ProjectOut | null>(null);
  const [spec, setSpec] = useState<ProjectSpec | null>(null);
  const [res, setRes] = useState<OptimisationResult | null>(null);
  const [resAt, setResAt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [tab, setTab] = useState<"run" | "verify" | "history" | "export">("run");
  const [verifyKey, setVerifyKey] = useState(0);
  const [recTab, setRecTab] = useState<"results" | "plan" | "saved">("results");
  const [plansKey, setPlansKey] = useState(0);
  const qTab = query.get("tab");
  const qAdd = query.get("add");
  useEffect(() => {
    if (qTab === "plan" || qTab === "saved" || qTab === "results") setRecTab(qTab);
  }, [qTab, qAdd]);

  const load = useCallback(async () => {
    try {
      const p = await api.project(projectId);
      setProject(p);
      setSpec(p.spec);
      // Results survive a reload: show the latest stored analysis of this project.
      const runs = await history.runs(projectId);
      const last = runs.find((r) => r.kind === "optimise");
      if (last) {
        const full = await history.run<OptimisationResult>(projectId, last.id);
        setRes(full.result);
        setResAt(full.created_at);
      }
    } catch (e) {
      if ((e as { status?: number }).status === 404) setNotFound(true);
      else setError(msg(e));
    }
  }, [projectId]);
  useEffect(() => {
    load();
  }, [load]);

  const dirty = useMemo(() => !!project && !!spec && JSON.stringify(project.spec) !== JSON.stringify(spec), [project, spec]);
  const stale = dirty && !!res;

  async function save() {
    if (!spec) return;
    setBusy(true);
    setError(null);
    try {
      setProject(await api.save(projectId, spec));
    } catch (e) {
      setError(msg(e));
    } finally {
      setBusy(false);
    }
  }

  async function analyse() {
    if (!spec) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await api.save(projectId, spec);
      setProject(saved);
      setRes(await api.optimise(projectId));
      setResAt(new Date().toISOString());
      navigate(`/p/${projectId}/recommendations`);
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError(msg(e));
    } finally {
      setBusy(false);
    }
  }

  if (notFound) {
    return (
      <section className="panel">
        <h2>Project not found</h2>
        <p>It may have been deleted, or it belongs to another workspace. Switch workspace at the top, or go back to your projects.</p>
        <a className="btn-link" href="#/">Back to projects</a>
      </section>
    );
  }
  if (!spec || !project) {
    return (
      <div className="panel skeleton" aria-busy="true">
        <div className="sk-line w60" /><div className="sk-line w90" /><div className="sk-line w75" />
        {error && <p className="error" role="alert">{error}</p>}
      </div>
    );
  }

  const model = models.find((m) => m.id === spec.model_id);
  const device = devices.find((d) => d.id === spec.device_id);
  const needsResult = (
    <section className="panel empty-state">
      <h2>No analysis yet</h2>
      <p>Choose the model, hardware and requirements, then run the analysis. Results are stored with the project.</p>
      <a className="btn-link primary" href={`#/p/${projectId}/input`}>Go to model and hardware</a>
    </section>
  );
  const goLegacy = (p: string) =>
    navigate(`/p/${projectId}/${({ start: "input", results: "recommendations", explore: "energy", export: "verify", verify: "verify" } as Record<string, string>)[p] ?? "input"}`);

  return (
    <>
      <div className="project-head">
        <div>
          <h1>{spec.name}</h1>
          <p className="muted">
            {model?.name ?? spec.model_id} on {device?.name ?? spec.device_id}, inputs version {project.version}
          </p>
        </div>
        <div className="project-head-right">
          {res && <span className="badge badge-analytical" title="Physics-model prediction with stated assumptions; measured values are labelled where they exist">predicted</span>}
          {stale && <span className="badge badge-assumed" title="The inputs changed since the last analysis">inputs changed since this analysis</span>}
        </div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}

      {area === "input" && (
        <InputPage
          spec={spec}
          setSpec={(s) => setSpec(s)}
          models={models}
          devices={devices}
          projectId={projectId}
          canWrite={canWrite}
          onModelAdded={(m) => {
            setModels((prev) => [...prev.filter((x) => x.id !== m.id), m]);
            setSpec((s) => (s ? { ...s, model_id: m.id } : s));
          }}
          onDevicesChanged={refreshLibrary}
        />
      )}
      {area === "constraints" && <ConstraintsPage spec={spec} setSpec={(s) => setSpec(s)} device={device} canWrite={canWrite} />}
      {(area === "input" || area === "constraints") && (
        <div className="actionbar" role="region" aria-label="Save and analyse">
          <div className="ab-summary">
            <span>
              <strong>{model?.name ?? spec.model_id}</strong> on <strong>{device?.name ?? spec.device_id}</strong>
            </span>
            <span className="muted">
              {spec.workload.fps} inputs/s, at most {spec.constraints.max_power_w} W, {spec.workload.ambient_c} °C ambient
              {dirty ? ", unsaved changes" : ""}
            </span>
            {!canWrite && <small className="ab-caveat">Your role in this workspace is read-only.</small>}
          </div>
          <div className="ab-actions">
            {area === "input" && <a className="btn-link" href={`#/p/${projectId}/constraints`}>Next: constraints</a>}
            <button disabled={busy || !canWrite || !dirty} onClick={save}>Save as version {project.version + (dirty ? 1 : 0)}</button>
            <button className="primary big" disabled={busy || !canWrite} onClick={analyse}>{busy ? "Analysing…" : "Analyse"}</button>
          </div>
        </div>
      )}
      {area === "recommendations" &&
        (res ? (
          <>
            <div className="tabs" role="tablist" aria-label="Recommendations">
              {(["results", "plan", "saved"] as const).map((t) => (
                <button key={t} role="tab" aria-selected={recTab === t} className={`tab ${recTab === t ? "on" : ""}`} onClick={() => setRecTab(t)}>
                  {{ results: "Verdict and recommendations", plan: "Build a design plan", saved: "Saved plans" }[t]}
                </button>
              ))}
            </div>
            {recTab === "results" && <ResultsPage res={res} spec={spec} go={goLegacy} />}
            {recTab === "plan" && (
              <PlanBuilder
                key={`${resAt}-${qAdd ?? ""}`}
                projectId={projectId}
                canWrite={canWrite}
                initialAdd={qAdd}
                onSaved={() => setPlansKey((k) => k + 1)}
              />
            )}
            {recTab === "saved" && <SavedPlans projectId={projectId} refreshKey={plansKey} />}
          </>
        ) : (
          needsResult
        ))}
      {area === "system-map" && <SystemMapPage projectId={projectId} version={project.version} hasBest={!!res?.best} />}
      {area === "timeline" && <TimelinePage projectId={projectId} version={project.version} hasBest={!!res?.best} />}
      {area === "memory" && <MemoryPage projectId={projectId} version={project.version} hasBest={!!res?.best} />}
      {area === "thermal" && <ThermalPage projectId={projectId} version={project.version} hasBest={!!res?.best} />}
      {area === "energy" && <EnergyPage projectId={projectId} version={project.version} hasBest={!!res?.best} res={res} spec={spec} />}
      {area === "verify" && (
        <>
          <div className="tabs" role="tablist" aria-label="Verify, history and export">
            {(["run", "verify", "history", "export"] as const).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} className={`tab ${tab === t ? "on" : ""}`} onClick={() => setTab(t)}>
                {{ run: "Run on this server", verify: "Predicted vs measured", history: "History", export: "Export" }[t]}
              </button>
            ))}
          </div>
          {tab === "run" && <ExecutionPanel projectId={projectId} canWrite={canWrite} onMeasured={() => setVerifyKey((k) => k + 1)} />}
          {tab === "verify" && <VerifyPage key={verifyKey} devices={devices} models={models} onChanged={() => setRes(null)} />}
          {tab === "history" && <HistoryPanel projectId={projectId} canWrite={canWrite} onRestored={load} />}
          {tab === "export" && <ExportPanel projectId={projectId} canWrite={canWrite} />}
        </>
      )}
      {resAt && area !== "input" && <p className="foot">Showing the analysis stored {new Date(resAt).toLocaleString()}. Predictions come from a physics model with stated assumptions; measured values are labelled as measured.</p>}

      {agentOpen && <div className="scrim" onClick={closeAgent} />}
      <aside className={`drawer ${agentOpen ? "open" : ""}`} aria-hidden={!agentOpen} aria-label="Assistant">
        <button className="drawer-close" onClick={closeAgent} aria-label="Close the assistant">×</button>
        {agentOpen && <AgentPanel projectId={projectId} onProjectChanged={load} />}
      </aside>
    </>
  );
}
