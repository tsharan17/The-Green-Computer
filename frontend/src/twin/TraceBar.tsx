import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { download, twin } from "../api";
import type { Config } from "../types";
import type { StoredTrace } from "./types";

export type Which = "baseline" | "best" | "plan";

/** A design plan the user analysed in Recommendations; the stage views can then show its trace. */
export interface PlanPick { key: string; label: string; config: Config }

/** One trace selection shared by every stage of a project: the setup chosen on one page stays
 * chosen on the next, and a trace computed once is reused. Keyed by setup, project version and the
 * analysis run, so a new analysis never shows a stale trace. */
function useTraceStore(projectId: number, version: number, hasBest: boolean, runKey: number | null) {
  const [which, setWhich] = useState<Which>(hasBest ? "best" : "baseline");
  const [plan, setPlan] = useState<PlanPick | null>(null);
  const chose = useRef(false);
  const choose = useCallback((w: Which) => {
    chose.current = true;
    setWhich(w);
  }, []);
  const [data, setData] = useState<StoredTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cache = useRef(new Map<string, StoredTrace>());

  const load = useCallback(
    async (force = false) => {
      if (which === "plan" && !plan) return;
      const key = `${which === "plan" ? `plan:${plan?.key}` : which}:${version}:${runKey ?? 0}`;
      const hit = cache.current.get(key);
      if (hit && !force) {
        setData(hit);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const t = await twin.create(projectId, which === "plan" ? "custom" : which, which === "plan" ? plan?.config : undefined);
        cache.current.set(key, t);
        setData(t);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [projectId, version, runKey, which, plan],
  );

  // The recommended setup becomes the default as soon as an analysis exists, unless the user already chose.
  useEffect(() => {
    if (hasBest && !chose.current) setWhich("best");
  }, [hasBest, runKey]);
  // A plan analysed against an earlier analysis no longer applies.
  useEffect(() => {
    setPlan(null);
  }, [runKey]);
  useEffect(() => {
    if (which === "best" && !hasBest) setWhich("baseline");
    if (which === "plan" && !plan) setWhich(hasBest ? "best" : "baseline");
  }, [hasBest, which, plan]);
  return { which, setWhich: choose, plan, setPlan, data, loading, error, load, recompute: () => load(true) };
}

type TraceStore = ReturnType<typeof useTraceStore>;
const TraceCtx = createContext<TraceStore | null>(null);

export function TraceProvider({ projectId, version, hasBest, runKey, children }: { projectId: number; version: number; hasBest: boolean; runKey: number | null; children: ReactNode }) {
  const store = useTraceStore(projectId, version, hasBest, runKey);
  return <TraceCtx.Provider value={store}>{children}</TraceCtx.Provider>;
}

/** Fetch (or reuse) the predicted trace for the setup chosen for this project. */
export function useTrace(projectId: number, version: number, hasBest: boolean) {
  const shared = useContext(TraceCtx);
  const local = useTraceStore(projectId, version, hasBest, null);
  const s = shared ?? local;
  const { load } = s;
  useEffect(() => {
    load();
  }, [load]);
  return s;
}

/** Tell the stage views which analysed plan to offer next to the current and recommended setups. */
export function usePlanPicker() {
  return useContext(TraceCtx)?.setPlan ?? null;
}
const PROV: Record<string, string> = {
  analytical: "Predicted by the analytical engine",
  calibrated: "Predicted, calibrated against your measurements",
  estimated: "Measured total, predicted split between operators",
  measured: "Measured on a real run",
  imported: "Imported from a device log",
};

export function TraceBar({
  projectId,
  state,
  hasBest,
  csvTable,
}: {
  projectId: number;
  state: ReturnType<typeof useTrace>;
  hasBest: boolean;
  csvTable?: "events" | "memory" | "tensors";
}) {
  const { which, setWhich, data, loading, error, recompute } = state;
  const t = data?.trace;
  return (
    <div className="tracebar" role="region" aria-label="Trace selection">
      <div className="seg" role="radiogroup" aria-label="Which setup">
        <button role="radio" aria-checked={which === "baseline"} className={which === "baseline" ? "on" : ""} onClick={() => setWhich("baseline")}>
          Current setup
        </button>
        <button
          role="radio"
          aria-checked={which === "best"}
          className={which === "best" ? "on" : ""}
          disabled={!hasBest}
          title={hasBest ? undefined : "Run the analysis to get a recommended setup"}
          onClick={() => setWhich("best")}
        >
          Recommended setup
        </button>
        {state.plan && (
          <button role="radio" aria-checked={which === "plan"} className={which === "plan" ? "on" : ""} title={state.plan.label} onClick={() => setWhich("plan")}>
            Chosen plan
          </button>
        )}
      </div>
      {t && (
        <span className={`badge ${t.kind === "measured" ? "badge-measured" : "badge-analytical"}`} title={t.source}>
          {PROV[t.provenance] ?? t.provenance}
        </span>
      )}
      {loading && <span className="muted">Computing the trace…</span>}
      <span className="grow" />
      {data && (
        <>
          <button className="link" onClick={() => download(`/projects/${projectId}/traces/${data.id}/export?format=json`, "trace.json")}>
            Trace JSON
          </button>
          {csvTable && (
            <button className="link" onClick={() => download(`/projects/${projectId}/traces/${data.id}/export?format=csv&table=${csvTable}`, `trace-${csvTable}.csv`)}>
              {csvTable === "events" ? "Events CSV" : csvTable === "memory" ? "Memory CSV" : "Tensors CSV"}
            </button>
          )}
          <button className="link" onClick={recompute} disabled={loading}>Recompute</button>
        </>
      )}
      {error && <p className="error full" role="alert">{error}</p>}
      {which === "plan" && <p className="note full">The chosen plan shows its model, runtime and configuration changes. Chip-design what-ifs are directional and are not drawn here.</p>}
      {t && t.fidelity !== "graph" && <p className="note full">{t.fidelity_note}</p>}
    </div>
  );
}
