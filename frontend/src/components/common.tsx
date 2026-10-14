import type { Config, EvaluationResult, Feasibility, Metric } from "../types";

export const STATE_LABEL: Record<Feasibility, string> = {
  verified_feasible: "Verified feasible",
  predicted_feasible: "Predicted feasible",
  uncertain: "Uncertain",
  infeasible: "Infeasible",
  verified_infeasible: "Verified infeasible",
};

export const METRIC_ROWS: [string, string][] = [
  ["latency", "Latency (per batch)"],
  ["capacity_fps", "Throughput capacity"],
  ["power_avg", "Average power"],
  ["power_peak", "Peak power"],
  ["energy_per_inference", "Energy per inference"],
  ["temperature", "Steady temperature (after governor)"],
  ["temperature_unthrottled", "Temperature without governor"],
  ["thermal_headroom", "Thermal headroom"],
  ["clock_factor", "Governor clock factor"],
  ["memory", "Memory"],
  ["accuracy", "Accuracy"],
  ["cost_per_day", "Electricity cost"],
  ["carbon_per_day", "Carbon"],
];

export function fmt(n: number): string {
  const a = Math.abs(n);
  if (a >= 1000) return n.toFixed(0);
  if (a >= 100) return n.toFixed(0);
  if (a >= 10) return n.toFixed(1);
  return n.toFixed(2);
}

export function Chip({ state }: { state: Feasibility }) {
  return <span className={`chip chip-${state}`}>{STATE_LABEL[state]}</span>;
}

export function Badge({ p }: { p: Metric["provenance"] }) {
  return <span className={`badge badge-${p}`}>{p.replace("_", " ")}</span>;
}

export function configLabel(c: Config): string {
  const extra = [
    c.resolution_scale !== 1 ? `res ${Math.round(c.resolution_scale * 100)}%` : "",
    c.clock_trim !== 1 ? `clock ${Math.round(c.clock_trim * 100)}%` : "",
  ].filter(Boolean);
  return [
    c.precision.toUpperCase(),
    `batch ${c.batch}`,
    c.power_mode_id,
    c.cooling_id,
    ...extra,
  ].join(" · ");
}

export function MetricTable({ r }: { r: EvaluationResult }) {
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>Metric</th>
          <th>Value</th>
          <th>Envelope (best – worst case)</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {METRIC_ROWS.map(([k, label]) => {
          const m = r.metrics[k];
          if (!m) return null;
          return (
            <tr key={k}>
              <td>{label}</td>
              <td>
                <strong>{fmt(m.value)}</strong> {m.unit}
              </td>
              <td className="muted">
                {fmt(m.low)} – {fmt(m.high)}
              </td>
              <td>
                <Badge p={m.provenance} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function Checks({ r }: { r: EvaluationResult }) {
  return (
    <ul className="checks">
      {r.checks.map((c) => (
        <li key={c.name} className={`check check-${c.status}`}>
          <span className="check-dot" />
          <span>
            <strong>{c.name}</strong> {c.sense} {fmt(c.limit)} {c.unit}
            <span className="muted">
              {" "}
              — worst case {fmt(c.pessimistic)}, best case {fmt(c.optimistic)}
              {c.note ? ` (${c.note})` : ""}
            </span>
          </span>
          <span className="check-status">{c.status}</span>
        </li>
      ))}
    </ul>
  );
}
