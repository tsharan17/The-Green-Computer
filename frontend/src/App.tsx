import VerifyEmail from "./pages/VerifyEmail";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, auth, history, setWorkspace } from "./api";
import AgentPanel from "./components/AgentPanel";
import DecisionBar from "./components/DecisionBar";
import ErrorBoundary from "./components/ErrorBoundary";
import ExecutionPanel from "./components/ExecutionPanel";
import ExportPanel from "./components/ExportPanel";
import GlobalSearch from "./components/GlobalSearch";
import { ErrorNote } from "./components/Help";
import HistoryPanel from "./components/HistoryPanel";
import Logo from "./components/Logo";
import PlanBuilder from "./components/PlanBuilder";
import SavedPlans from "./components/SavedPlans";
import StatusBar from "./components/StatusBar";
import { ModeProvider, useMode } from "./lib/mode";
import AccountPage from "./pages/AccountPage";
import AuthPage from "./pages/AuthPage";
import CapabilitiesPage from "./pages/CapabilitiesPage";
import ConstraintsPage from "./pages/ConstraintsPage";
import InputPage from "./pages/InputPage";
import ResultsPage from "./pages/ResultsPage";
import StartGuide from "./pages/StartGuide";
import SummaryPage from "./pages/SummaryPage";
import VerifyPage from "./pages/VerifyPage";
import WorkspacePage from "./pages/WorkspacePage";
import LegalPage, { LegalLinks } from "./pages/LegalPage";
import CoolingFigures from "./workflow/CoolingFigures";
import PipelineStrip from "./workflow/PipelineStrip";
import RecommendationCatalogue from "./workflow/RecommendationCatalogue";
import VerificationPanel from "./workflow/VerificationPanel";
import { AREAS, type AreaId, navigate, useRoute } from "./router";
import MemoryPage from "./twin/MemoryPage";
import SystemMapPage from "./twin/SystemMapPage";
import { EnergyPage, ThermalPage } from "./twin/ThermalEnergyPages";
import { TraceProvider } from "./twin/TraceBar";
import TimelinePage from "./twin/TimelinePage";
import type { HardwareProfile, Me, ModelProfile, OptimisationResult, ProjectOut, ProjectSpec } from "./types";

const WS_KEY = "gc_workspace";

/** The workflow, in order: what the navigation rail groups and how a project moves through it. */
const STAGES: { title: string; ids: readonly AreaId[] }[] = [
  { title: "Define", ids: ["input", "constraints", "check"] },
  { title: "Analyse", ids: ["summary", "system-map", "timeline", "memory", "thermal", "energy"] },
  { title: "Decide", ids: ["recommendations"] },
  { title: "Hand over", ids: ["verify"] },
];

function readWs(): number | null {
  try {
    return Number(localStorage.getItem(WS_KEY)) || null;
  } catch {
    return null;
  }
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
  if (page === "verify-email") return <VerifyEmail token={route.query.get("token") ?? ""} onDone={loadMe} />;
  if (page === "legal") return <LegalPage doc={route.parts[1] ?? "terms"} />;
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
          navigate(mode === "signup" ? "/start" : "/");
        }}
      />
    );
  }
  return (
    <ModeProvider signedIn>
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
    </ModeProvider>
  );
}

function ModeSwitch() {
  const { mode, setMode } = useMode();
  return (
    <div className="seg mode-switch" role="radiogroup" aria-label="Display">
      <button role="radio" aria-checked={mode === "simple"} className={mode === "simple" ? "on" : ""} onClick={() => setMode("simple")}
        title="Plain answers first; engineering detail one click away">Simple</button>
      <button role="radio" aria-checked={mode === "engineering"} className={mode === "engineering" ? "on" : ""} onClick={() => setMode("engineering")}
        title="Engineering detail open by default">Engineering</button>
    </div>
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
  const { mode } = useMode();
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [devices, setDevices] = useState<HardwareProfile[]>([]);
  const [libError, setLibError] = useState<unknown>(null);
  const [agentOpen, setAgentOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const refreshLibrary = useCallback(async () => {
    try {
      const [m, d] = await Promise.all([api.models(), api.devices()]);
      setModels(m);
      setDevices(d);
      setLibError(null);
    } catch (e) {
      setLibError(e);
    }
  }, []);
  useEffect(() => {
    refreshLibrary();
  }, [refreshLibrary, me.active_workspace_id]);

  const [p0, p1, p2] = route.parts;
  const projectId = p0 === "p" && p1 ? Number(p1) : null;
  const area = (AREAS.some((a) => a.id === p2) ? p2 : null) as AreaId | null;
  const canWrite = me.role === "owner" || me.role === "editor";
  const link = (a: (typeof AREAS)[number]) => (
    <a key={a.id} className={`rail-item ${area === a.id ? "on" : ""}`} href={`#/p/${projectId}/${a.id}`} aria-current={area === a.id ? "page" : undefined}>
      <span className="rail-dot" aria-hidden />
      <span className="rail-text"><strong>{a.label}</strong><small>{a.sub}</small></span>
    </a>
  );
  const stage = (ids: readonly AreaId[]) => {
    const items = ids.map((id) => AREAS.find((a) => a.id === id)!);
    if (mode === "engineering") return items.map(link);
    const eng = items.filter((a) => a.group === "engineering");
    return (
      <>
        {items.filter((a) => a.group === "main").map(link)}
        {eng.length > 0 && (
          <details className="nav-more" open={eng.some((a) => a.id === area)}>
            <summary>Engineering views ({eng.length})</summary>
            {eng.map(link)}
          </details>
        )}
      </>
    );
  };

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
        <nav className="rail" aria-label="Workflow">
          <a className={`rail-item ${!projectId && !p0 ? "on" : ""}`} href="#/" aria-current={!projectId && !p0 ? "page" : undefined}>
            <span className="rail-dot" aria-hidden />
            <span className="rail-text"><strong>Workspace</strong><small>Projects and onboarding</small></span>
          </a>
          {projectId !== null &&
            STAGES.map((s) => (
              <div className="rail-group" key={s.title}>
                <span className="rail-title">{s.title}</span>
                {stage(s.ids)}
              </div>
            ))}
        </nav>
        {projectId !== null && (
          <button className="agent-btn" onClick={() => setAgentOpen(true)}>
            Ask the assistant
          </button>
        )}
        <a className={`cap-link ${p0 === "capabilities" ? "on" : ""}`} href="#/capabilities">What this installation can do</a>
        <StatusBar />
        <LegalLinks />
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
          <GlobalSearch />
          <ModeSwitch />
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
          {me.user.verification_required && !me.user.email_verified && (
            <p className="verify-banner" role="status">
              <span aria-hidden>!</span> Confirm your email to make changes: open the link we sent to {me.user.email}, or <a href="#/account">send a new one</a>.
            </p>
          )}
          {!!me.terms?.outstanding.length && <TermsBanner onAccepted={reloadMe} docs={me.terms.outstanding} />}
          <ErrorNote error={libError} onRetry={refreshLibrary} />
          <ErrorBoundary>
            {p0 === "account" ? (
              <AccountPage me={me} onChanged={reloadMe} onDeleted={signedOut} />
            ) : p0 === "capabilities" ? (
              <CapabilitiesPage />
            ) : p0 === "start" ? (
              <StartGuide models={models} devices={devices} onModelAdded={(m) => setModels((prev) => [...prev.filter((x) => x.id !== m.id), m])} />
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

function TermsBanner({ docs, onAccepted }: { docs: string[]; onAccepted: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const names: Record<string, string> = { terms: "Terms and Conditions", privacy: "Privacy Policy" };
  return (
    <div className="verify-banner" role="status">
      <span aria-hidden>!</span>
      <span>
        The {docs.map((d) => names[d] ?? d).join(" and ")} changed. Please read{" "}
        {docs.map((d, i) => <span key={d}>{i > 0 && " and "}<a href={`#/legal/${d}`}>{names[d] ?? d}</a></span>)} and accept to continue.
      </span>
      <button disabled={busy} onClick={async () => {
        setBusy(true);
        try {
          await auth.acceptTerms();
          onAccepted();
        } catch (e) {
          setError(e);
        } finally {
          setBusy(false);
        }
      }}>{busy ? "Saving…" : "I have read and accept"}</button>
      <ErrorNote error={error} />
    </div>
  );
}

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
  area: AreaId | null;
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
  const [runId, setRunId] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notFound, setNotFound] = useState(false);
  const [tab, setTab] = useState<"run" | "verify" | "history" | "export">("run");
  const [verifyKey, setVerifyKey] = useState(0);
  const [recTab, setRecTab] = useState<"results" | "catalogue" | "plan" | "saved">("results");
  const [plansKey, setPlansKey] = useState(0);
  const qTab = query.get("tab");
  const qAdd = query.get("add");
  useEffect(() => {
    if (qTab === "plan" || qTab === "saved" || qTab === "results" || qTab === "catalogue") setRecTab(qTab);
    if (qTab === "run" || qTab === "verify" || qTab === "history" || qTab === "export") setTab(qTab);
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
        setRunId(last.id);
      }
      setLoaded(true);
    } catch (e) {
      if ((e as { status?: number }).status === 404) setNotFound(true);
      else setError(e);
    }
  }, [projectId]);
  useEffect(() => {
    load();
  }, [load]);

  // A bare project link opens the answer when there is one, else the inputs.
  useEffect(() => {
    if (loaded && area === null) navigate(`/p/${projectId}/${res ? "summary" : "input"}`);
  }, [loaded, area, res, projectId]);

  const dirty = useMemo(() => !!project && !!spec && JSON.stringify(project.spec) !== JSON.stringify(spec), [project, spec]);
  const stale = dirty && !!res;

  async function save() {
    if (!spec) return;
    setBusy(true);
    setError(null);
    try {
      setProject(await api.save(projectId, spec));
    } catch (e) {
      setError(e);
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
      const runs = await history.runs(projectId);
      setRunId(runs.find((r) => r.kind === "optimise")?.id ?? null);
      navigate(`/p/${projectId}/summary`);
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (notFound) {
    return (
      <section className="panel">
        <h1>Project not found</h1>
        <p>It may have been deleted, or it belongs to another workspace. Switch workspace at the top, or go back to your projects.</p>
        <a className="btn-link" href="#/">Back to projects</a>
      </section>
    );
  }
  if (!spec || !project) {
    return (
      <div className="panel skeleton" aria-busy="true">
        <div className="sk-line w60" /><div className="sk-line w90" /><div className="sk-line w75" />
        <ErrorNote error={error} onRetry={load} />
      </div>
    );
  }

  const model = models.find((m) => m.id === spec.model_id);
  const device = devices.find((d) => d.id === spec.device_id);
  const needsResult = (
    <section className="panel empty-state">
      <h2>No analysis yet</h2>
      <p>The inputs are set. Run the analysis to get a verdict, the biggest bottleneck and a recommended change; it takes a few seconds.</p>
      <div className="actions">
        <button className="primary" disabled={busy || !canWrite} onClick={analyse}>{busy ? "Analysing…" : "Analyse now"}</button>
        <a className="btn-link" href={`#/p/${projectId}/input`}>Review the inputs first</a>
      </div>
    </section>
  );
  const goLegacy = (p: string) =>
    navigate(`/p/${projectId}/${({ start: "input", results: "recommendations", explore: "energy", export: "verify", verify: "verify" } as Record<string, string>)[p] ?? "input"}`);

  return (
    <TraceProvider projectId={projectId} version={project.version} hasBest={!!res?.best} runKey={runId}>
      <div className="project-head">
        <div>
          <h1>{spec.name}</h1>
          <p className="muted">
            {model?.name ?? spec.model_id} on {device?.name ?? spec.device_id}, inputs version {project.version}
          </p>
        </div>
      </div>
      <PipelineStrip projectId={projectId} refreshKey={`${project.version}-${runId}-${plansKey}-${area}`} />
      <DecisionBar project={project} res={res} stale={stale || (!!res && dirty)} busy={busy} canWrite={canWrite} model={model} device={device} onAnalyse={analyse} />
      <ErrorNote error={error} onRetry={() => setError(null)} />

      {area === "summary" && (res ? <SummaryPage res={res} spec={spec} projectId={projectId} runId={runId} /> : needsResult)}
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
      {area === "check" && (
        <>
          <VerificationPanel projectId={projectId} refreshKey={`${project.version}-${dirty}`} />
          {dirty && <p className="note-warn" role="status">You have unsaved changes; the report shows the saved version {project.version}. Save to check the new inputs.</p>}
          <div className="actions">
            <button disabled={busy || !canWrite || !dirty} onClick={save}>Save changes</button>
            <button className="primary" disabled={busy || !canWrite} onClick={analyse}>{busy ? "Analysing…" : "Analyse"}</button>
          </div>
        </>
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
            {area === "constraints" && <a className="btn-link" href={`#/p/${projectId}/check`}>Next: verification</a>}
            <button disabled={busy || !canWrite || !dirty} onClick={save}>Save as version {project.version + (dirty ? 1 : 0)}</button>
            <button className="primary big" disabled={busy || !canWrite} onClick={analyse}>{busy ? "Analysing…" : "Analyse"}</button>
          </div>
        </div>
      )}
      {area === "recommendations" &&
        (res ? (
          <>
            <div className="tabs" role="tablist" aria-label="Recommendations">
              {(["results", "catalogue", "plan", "saved"] as const).map((t) => (
                <button key={t} role="tab" aria-selected={recTab === t} className={`tab ${recTab === t ? "on" : ""}`} onClick={() => setRecTab(t)}>
                  {{ results: "Verdict", catalogue: "Software and hardware", plan: "Build and compare a plan", saved: "Saved plans" }[t]}
                </button>
              ))}
            </div>
            {recTab === "results" && <ResultsPage res={res} spec={spec} go={goLegacy} />}
            {recTab === "catalogue" && <RecommendationCatalogue projectId={projectId} canWrite={canWrite} refreshKey={`${runId}-${plansKey}`} />}
            {recTab === "plan" && (
              <PlanBuilder key={`${resAt}-${qAdd ?? ""}`} projectId={projectId} canWrite={canWrite} initialAdd={qAdd} onSaved={() => setPlansKey((k) => k + 1)} />
            )}
            {recTab === "saved" && <SavedPlans projectId={projectId} refreshKey={plansKey} />}
          </>
        ) : (
          needsResult
        ))}
      {area === "system-map" && <SystemMapPage projectId={projectId} version={project.version} hasBest={!!res?.best} />}
      {area === "timeline" && <TimelinePage projectId={projectId} version={project.version} hasBest={!!res?.best} />}
      {area === "memory" && <MemoryPage projectId={projectId} version={project.version} hasBest={!!res?.best} />}
      {area === "thermal" && (
        <>
          <ThermalPage projectId={projectId} version={project.version} hasBest={!!res?.best} />
          <CoolingFigures projectId={projectId} version={project.version} />
        </>
      )}
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
    </TraceProvider>
  );
}
