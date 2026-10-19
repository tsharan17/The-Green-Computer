import { useCallback, useEffect, useRef, useState } from "react";
import { download, twin } from "../api";
import type { StoredTrace } from "./types";

export type Which = "baseline" | "best";

/** Fetch (or compute) the predicted trace for the current setup or the recommended one. Cached per
 * (setup, project version) for the session; "Recompute" forces a new stored trace. */
export function useTrace(projectId: number, version: number, hasBest: boolean) {
  const [which, setWhich] = useState<Which>(hasBest ? "best" : "baseline");
  const [data, setData] = useState<StoredTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cache = useRef(new Map<string, StoredTrace>());

  const load = useCallback(
    async (force = false) => {
      const key = `${which}:${version}`;
      const hit = cache.current.get(key);
      if (hit && !force) {
        setData(hit);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const t = await twin.create(projectId, which);
        cache.current.set(key, t);
        setData(t);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [projectId, version, which],
  );

  useEffect(() => {
    if (which === "best" && !hasBest) setWhich("baseline");
  }, [hasBest, which]);
  useEffect(() => {
    load();
  }, [load]);
  return { which, setWhich, data, loading, error, recompute: () => load(true) };
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
      {t && t.fidelity !== "graph" && <p className="note full">{t.fidelity_note}</p>}
    </div>
  );
}
