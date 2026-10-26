import { useEffect, useState } from "react";
import { workflow } from "../api";
import type { Pipeline, Stage, StageState } from "./types";

/** Where each workflow stage stands for this project, from the server's stored records. A stage is
 * done, ready (its inputs are there), blocked (an earlier stage must finish) or stale (the inputs it
 * used have changed; the record is kept). */
const AREA_OF: Record<Stage["id"], string> = {
  input: "input", verification: "check", analysis: "summary", recommendations: "recommendations",
  validation: "recommendations?tab=plan", results: "verify?tab=export",
};
const STATE_TEXT: Record<StageState, string> = { done: "Done", ready: "Ready", blocked: "Waiting", stale: "Out of date" };

export default function PipelineStrip({ projectId, refreshKey }: { projectId: number; refreshKey: string }) {
  const [p, setP] = useState<Pipeline | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let live = true;
    workflow.pipeline(projectId).then((x) => live && (setP(x), setError(false))).catch(() => live && setError(true));
    return () => {
      live = false;
    };
  }, [projectId, refreshKey]);
  if (error) return <p className="hint" role="status">Workflow status is unavailable right now; the pages below still work.</p>;
  if (!p) return <div className="pipeline pipeline-loading" aria-busy="true" />;
  return (
    <nav className="pipeline" aria-label="Workflow stages">
      <ol>
        {p.stages.map((s, i) => (
          <li key={s.id} className={`pl-${s.state}${p.next === s.id ? " pl-next" : ""}`}>
            <a href={`#/p/${projectId}/${AREA_OF[s.id]}`} title={s.summary}>
              <span className="pl-n" aria-hidden>{i + 1}</span>
              <span className="pl-text">
                <strong>{s.title}</strong>
                <small>{STATE_TEXT[s.state]}</small>
              </span>
            </a>
          </li>
        ))}
      </ol>
      {p.stages.some((s) => s.state === "stale") && (
        <p className="pl-note">Some results are out of date because the inputs changed. They are kept; run the analysis again to add new ones.</p>
      )}
    </nav>
  );
}
