import type { HardwareProfile, ModelProfile, OptimisationResult, ProjectOut } from "../types";
import { Outcome } from "./Help";

/** The project's decision at a glance, on every project screen: where it stands, what to do. */
export default function DecisionBar({
  project,
  res,
  stale,
  busy,
  canWrite,
  model,
  device,
  onAnalyse,
}: {
  project: ProjectOut;
  res: OptimisationResult | null;
  stale: boolean;
  busy: boolean;
  canWrite: boolean;
  model?: ModelProfile;
  device?: HardwareProfile;
  onAnalyse: () => void;
}) {
  const s = project.spec;
  const v = res?.verdict;
  const rec = res?.advice.filter((a) => a.in_recommended) ?? [];
  const conf = rec.some((a) => a.confidence === "low") ? "Low" : rec.some((a) => a.confidence === "medium") ? "Medium" : rec.length ? "High" : "–";
  const saving = v?.savings?.energy_percent;
  const pid = project.id;

  let action: { label: string; href?: string; run?: boolean };
  if (!res || stale) action = { label: busy ? "Analysing…" : stale ? "Analyse the new inputs" : "Analyse", run: true };
  else if (res.best && !v?.baseline.ok) action = { label: "Review the recommended plan", href: `#/p/${pid}/recommendations?tab=plan` };
  else if (res.best) action = { label: "Export a summary", href: `#/p/${pid}/verify?tab=export` };
  else action = { label: "See what limits it", href: `#/p/${pid}/summary` };

  return (
    <section className="decision-bar" aria-label="Decision summary">
      <div className="db-cell">
        <span className="db-label">Current setup</span>
        <strong>{model?.name ?? s.model_id}</strong>
        <span className="db-sub">on {device?.name ?? s.device_id}, {s.workload.fps} inputs/s</span>
      </div>
      <div className="db-cell">
        <span className="db-label">Outcome today</span>
        <Outcome state={res?.baseline.feasibility} />
        {stale && <span className="db-sub warn-text">Inputs changed since this analysis</span>}
      </div>
      <div className="db-cell">
        <span className="db-label">Recommended plan</span>
        {res?.best ? (
          <>
            <strong>{rec.length || "No"} change{rec.length === 1 ? "" : "s"}</strong>
            <span className="db-sub"><Outcome state={res.best.feasibility} /></span>
          </>
        ) : (
          <span className="db-sub">{res ? "No setup meets every requirement" : "Analyse first"}</span>
        )}
      </div>
      <div className="db-cell">
        <span className="db-label">Expected improvement</span>
        <strong className="num">{saving !== undefined && saving !== null ? `${saving >= 0 ? "−" : "+"}${Math.abs(saving).toFixed(0)}% energy` : "–"}</strong>
        {v?.savings && <span className="db-sub num">{v.savings.power_percent.toFixed(0)}% less power</span>}
      </div>
      <div className="db-cell">
        <span className="db-label">Confidence</span>
        <strong>{conf}</strong>
        <span className="db-sub">{res ? "predicted, not measured" : ""}</span>
      </div>
      <div className="db-action">
        {action.run ? (
          <button className="primary" disabled={busy || !canWrite} onClick={onAnalyse}>{action.label}</button>
        ) : (
          <a className="btn-link primary" href={action.href}>{action.label}</a>
        )}
      </div>
    </section>
  );
}
