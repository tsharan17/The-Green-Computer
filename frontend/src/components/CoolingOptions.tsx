import { useEffect, useState } from "react";
import { plans } from "../api";
import { navigate } from "../router";
import { num } from "../twin/chart";
import type { CoolingRow } from "../types";

const RATING_CLASS: Record<string, string> = {
  "lower impact": "chip-predicted_feasible",
  "meets requirements": "chip-uncertain",
  "does not meet requirements": "chip-infeasible",
};

export default function CoolingOptions({ projectId, which }: { projectId: number; which: "baseline" | "best" }) {
  const [data, setData] = useState<{ criteria: string[]; rows: CoolingRow[]; assumptions: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyOk, setOnlyOk] = useState(true);

  useEffect(() => {
    setData(null);
    plans.cooling(projectId, which).then(setData).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [projectId, which]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!data) return <div className="panel skeleton" aria-busy="true"><div className="sk-line w75" /></div>;
  const rows = data.rows.filter((r) => !onlyOk || r.meets_requirements || r.id === "current");
  return (
    <section className="panel" aria-labelledby="cool-h">
      <div className="row">
        <h2 id="cool-h">Cooling options for this workload</h2>
        <label className="check-row"><input type="checkbox" checked={onlyOk} onChange={(e) => setOnlyOk(e.target.checked)} /> Only options that meet your requirements</label>
      </div>
      <p className="hint">Ranked by these stated criteria, in order:</p>
      <ol className="criteria">{data.criteria.map((c) => <li key={c}>{c}</li>)}</ol>
      <div className="table-wrap">
        <table className="tbl cooling">
          <thead>
            <tr><th>Option</th><th>Rating</th><th className="num">R_th (K/W)</th><th className="num">Fan/pump</th><th className="num">Temperature</th><th className="num">System power</th><th className="num">kgCO₂e / year</th><th>Upkeep</th><th><span className="sr-only">Plan</span></th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.name}</strong>
                  <small className="block muted">{r.materials}{r.cost_usd ? `, about $${r.cost_usd.low}–${r.cost_usd.high}` : ""}{r.noise_dba ? `, ${r.noise_dba} dBA` : ""}</small>
                  <small className="block muted">Source: {r.source} ({r.confidence} confidence)</small>
                </td>
                <td><span className={`chip ${RATING_CLASS[r.rating] ?? ""}`}>{r.rating}</span><small className="block muted">{r.explanation}</small></td>
                <td className="num">{num(r.r_th_k_per_w)}{r.r_th_range && <small className="block muted">{num(r.r_th_range.low)}–{num(r.r_th_range.high)}{r.modifier ? " ×" : ""}</small>}</td>
                <td className="num">{num(r.active_w)} W</td>
                <td className="num">{num(r.temperature_c)} °C{r.throttled && <small className="block bad">throttles to {(r.clock_factor * 100).toFixed(0)}%</small>}</td>
                <td className="num">{num(r.power_w)} W</td>
                <td className="num">{num(r.lifetime_kgco2e_per_year)}<small className="block muted">{num(r.operational_kgco2e_per_year)} use + {num(r.embodied_kgco2e_per_year)} made</small></td>
                <td className="muted">{r.maintainability}{r.recyclability ? ` Recyclability: ${r.recyclability}.` : ""}</td>
                <td>{r.change_id && r.meets_requirements && (
                  <button className="link" onClick={() => navigate(`/p/${projectId}/recommendations?tab=plan&add=${encodeURIComponent(r.change_id!)}`)}>Add to a plan</button>
                )}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="hint">{data.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
    </section>
  );
}
