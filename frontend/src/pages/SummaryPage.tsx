import { download } from "../api";
import { Checks, MetricTable, configLabel } from "../components/common";
import { Level, Outcome, Why } from "../components/Help";
import { BOTTLENECK_PLAIN } from "../lib/glossary";
import type { Advice, OptimisationResult, ProjectSpec } from "../types";

const TERM_FOR: Record<string, string> = { compute: "compute-bound", memory: "memory-bound", overhead: "overhead-bound", heat: "heat" };

/** Bars against a limit: today vs with the plan. A simple diagram for the "Explain" level. */
function LimitBars({ rows }: { rows: { label: string; unit: string; today: number; plan: number | null; limit: number | null; lower: boolean }[] }) {
  return (
    <div className="limit-bars" role="table" aria-label="Today and with the plan, against your limits">
      {rows.map((r) => {
        const max = Math.max(r.today, r.plan ?? 0, r.limit ?? 0) * 1.1 || 1;
        const ok = (v: number) => (r.limit === null ? null : r.lower ? v <= r.limit : v >= r.limit);
        const pct = (v: number) => `${(100 * v) / max}%`;
        return (
          <div className="lb-row" role="row" key={r.label}>
            <span className="lb-label" role="rowheader">{r.label}</span>
            <div className="lb-track" role="cell" aria-hidden>
              <span className={`lb-bar today ${ok(r.today) === false ? "over" : ""}`} style={{ width: pct(r.today) }} />
              {r.plan !== null && <span className={`lb-bar plan ${ok(r.plan) === false ? "over" : ""}`} style={{ width: pct(r.plan) }} />}
              {r.limit !== null && <span className="lb-limit" style={{ left: pct(r.limit) }} title={`Your limit: ${r.limit} ${r.unit}`} />}
            </div>
            <span className="lb-vals num" role="cell">
              <span>Today {r.today.toPrecision(3)} {r.unit}{ok(r.today) === false ? " ✕" : ""}</span>
              {r.plan !== null && <span>Plan {r.plan.toPrecision(3)} {r.unit}{ok(r.plan) === false ? " ✕" : r.limit !== null ? " ✓" : ""}</span>}
            </span>
            <span className="lb-lim muted" role="cell">{r.limit === null ? "no limit" : `limit ${r.lower ? "≤" : "≥"} ${r.limit} ${r.unit}`}</span>
          </div>
        );
      })}
    </div>
  );
}

function NextStep({ res, projectId }: { res: OptimisationResult; projectId: number }) {
  const plan = res.repair?.needed ? res.repair.plans[0] : null;
  const rec: Advice[] = res.advice.filter((a) => a.in_recommended);
  const lead = rec[0];
  if (!plan && !lead) {
    return (
      <section className="next-step">
        <h2>Recommended next step</h2>
        <p>{res.best ? "Your current setup already meets every requirement. The thermal and energy maps show how much margin it has." : "No change we can model makes this setup meet every requirement."}</p>
        <a className="btn-link primary" href={`#/p/${projectId}/${res.best ? "thermal" : "recommendations"}`}>{res.best ? "Open the thermal map" : "See the alternatives"}</a>
      </section>
    );
  }
  const fixText = plan ? plan.changes.map((c) => c.replace(/^(Software|Hardware \((configure|select)\)|AI model): /, "")).join("; ") : "";
  const saving = res.verdict?.savings?.energy_percent;
  const evidence = res.best?.metrics.latency.provenance === "measured" ? "Backed by a real measurement of this setup."
    : res.best?.metrics.latency.provenance === "calibrated" ? "Physics prediction, calibrated against real runs of this device."
    : "Physics prediction with stated assumptions; nothing here has been measured on your hardware yet.";
  return (
    <section className="next-step" aria-labelledby="ns-h">
      <h2 id="ns-h">Recommended next step</h2>
      <p className="ns-what">{lead ? rec.map((a) => a.action).join(" ") : fixText}</p>
      <dl className="ns-grid">
        <div><dt>Why</dt><dd>{lead?.why ?? "It is the smallest set of changes that makes every requirement pass."}</dd></div>
        <div><dt>Expected benefit</dt><dd>{saving !== null && saving !== undefined ? `${saving.toFixed(0)}% less energy per input${res.verdict?.baseline.ok ? "" : ", and every requirement passes"}.` : lead?.gain ?? ""}</dd></div>
        {plan && lead && <div><dt>Smallest fix</dt><dd>If you only want it to pass: {fixText} (fixes {plan.fixes.join(", ") || "every requirement"}; {plan.energy_saving_percent.toFixed(0)}% less energy).</dd></div>}
        <div><dt>Trade-off</dt><dd>{rec.flatMap((a) => a.tradeoffs).slice(0, 2).join(" ") || "None predicted beyond the effort to change it."}</dd></div>
        <div><dt>Confidence</dt><dd>{lead ? `${lead.confidence[0].toUpperCase()}${lead.confidence.slice(1)}: ${lead.confidence_reason}.` : "Medium: physics prediction."}</dd></div>
        <div><dt>Evidence</dt><dd>{evidence}</dd></div>
        <div><dt>How to check it</dt><dd>{(lead?.validate_steps ?? ["Benchmark it on the device"]).join("; ")}.</dd></div>
      </dl>
      <div className="actions">
        <a className="btn-link primary" href={`#/p/${projectId}/recommendations?tab=plan`}>Build this plan</a>
        <a className="btn-link" href={`#/p/${projectId}/recommendations`}>See every recommendation</a>
      </div>
    </section>
  );
}

export default function SummaryPage({ res, spec, projectId, runId }: { res: OptimisationResult; spec: ProjectSpec; projectId: number; runId: number | null }) {
  const v = res.verdict;
  const lf = res.limiting_factor ?? "";
  const [lfTitle, lfWhy] = lf.includes(":") ? [lf.slice(0, lf.indexOf(":")), lf.slice(lf.indexOf(":") + 1).trim()] : [lf, ""];
  const b = res.baseline;
  const best = res.best;
  const c = spec.constraints;
  const rows = [
    { label: "Average power", unit: "W", today: b.metrics.power_avg.value, plan: best ? best.metrics.power_avg.value : null, limit: c.max_power_w, lower: true },
    { label: "Latency per input", unit: "ms", today: b.metrics.latency.value, plan: best ? best.metrics.latency.value : null, limit: c.max_latency_ms, lower: true },
    { label: "Throughput", unit: "/s", today: b.metrics.capacity_fps.value, plan: best ? best.metrics.capacity_fps.value : null, limit: spec.workload.fps, lower: false },
    { label: "Temperature", unit: "°C", today: b.metrics.temperature_unthrottled.value, plan: best ? best.metrics.temperature_unthrottled.value : null, limit: null, lower: true },
  ];
  return (
    <div className="summary-page">
      <section className="verdict-band" aria-labelledby="vb-h">
        <div className="vb-outcomes">
          <span>Today</span> <Outcome state={b.feasibility} size="lg" />
          {best && (<><span aria-hidden>→</span><span>With the recommended plan</span> <Outcome state={best.feasibility} size="lg" /></>)}
        </div>
        <h2 id="vb-h" className="vb-sentence">{v?.summary ?? "Analysis complete."}</h2>
        {v?.baseline.problems.length ? (
          <ul className="vb-problems">{v.baseline.problems.map((p) => <li key={p}>{p}</li>)}</ul>
        ) : null}
      </section>

      <section className="bottleneck" aria-labelledby="bn-h2">
        <h2 id="bn-h2">Biggest bottleneck</h2>
        <p className="bn-main"><strong>{lfTitle ? lfTitle[0].toUpperCase() + lfTitle.slice(1) : "–"}</strong>{lfWhy ? `: ${lfWhy}.` : ""}</p>
        <p className="muted">Today the setup is limited by: {BOTTLENECK_PLAIN[b.bottleneck] ?? b.bottleneck}</p>
        <Why id={TERM_FOR[b.bottleneck] ?? "feasibility"} />
      </section>

      <NextStep res={res} projectId={projectId} />

      <Level kind="explain" title="Why this happened">
        <p>Each bar compares today with the recommended plan against the limits you set. A cross marks a missed requirement.</p>
        <LimitBars rows={rows} />
        <p className="hint">Temperature is shown without throttling: the level the chip would reach if it did not slow itself down. <Why id="throttling" /></p>
        {res.repair?.binding_constraints.length ? <p>The requirements that are hardest to meet: {res.repair.binding_constraints.join(", ")}.</p> : null}
      </Level>

      <Level kind="engineering" title="Every number, with its range and source">
        <p className="muted">Today: {configLabel(b.config)}{best ? `. Plan: ${configLabel(best.config)}` : ""}. Engine {b.engine_version}; {res.evaluated.toLocaleString()} settings searched.</p>
        <h3>Today</h3>
        <Checks r={b} />
        <MetricTable r={b} />
        {best && (<><h3>With the recommended plan</h3><Checks r={best} /><MetricTable r={best} /></>)}
        <div className="actions">
          {runId && <button onClick={() => download(`/projects/${projectId}/runs/${runId}`, `analysis-${runId}.json`)}>Download the full analysis (JSON)</button>}
          <a className="btn-link" href={`#/p/${projectId}/system-map`}>Open the engineering views</a>
        </div>
      </Level>
    </div>
  );
}
