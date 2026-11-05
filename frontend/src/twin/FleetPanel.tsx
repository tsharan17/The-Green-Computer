import { useEffect, useState } from "react";
import { BASE, baseHeaders } from "../api";

interface Fig { value: number; low: number; high: number; provenance: string }
interface Scaled { cost: Fig; carbon: Fig }
interface Fleet { today: Scaled; best: Scaled | null; excludes: string }

const big = (x: number) => Math.round(x).toLocaleString();

/** Cost and carbon for many units over years: the day's prediction scaled up, keeping its range. */
export default function FleetPanel({ projectId, runKey }: { projectId: number; runKey: unknown }) {
  const [units, setUnits] = useState(1000);
  const [years, setYears] = useState(3);
  const [out, setOut] = useState<Fleet | null>(null);
  useEffect(() => {
    let live = true;
    if (!(units >= 1 && years > 0)) return;
    fetch(`${BASE}/projects/${projectId}/fleet`, {
      method: "POST", credentials: "same-origin",
      headers: baseHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ units, years }),
    }).then((r) => (r.ok ? r.json() : null)).then((d) => live && setOut(d)).catch(() => live && setOut(null));
    return () => { live = false; };
  }, [projectId, units, years, runKey]);
  const row = (label: string, s: Scaled) => (
    <tr key={label}>
      <th scope="row">{label}</th>
      <td className="num">{big(s.cost.value)} <small>({big(s.cost.low)} to {big(s.cost.high)})</small></td>
      <td className="num">{big(s.carbon.value / 1000)} kg <small>({big(s.carbon.low / 1000)} to {big(s.carbon.high / 1000)})</small></td>
    </tr>
  );
  return (
    <section className="panel" aria-labelledby="fleet-h">
      <h2 id="fleet-h">Across a fleet</h2>
      <form className="inline-form" onSubmit={(e) => e.preventDefault()}>
        <label className="field">Units<input type="number" min={1} max={100000000} value={units} onChange={(e) => setUnits(Number(e.target.value))} /></label>
        <label className="field">Years<input type="number" min={0.1} max={30} step={0.5} value={years} onChange={(e) => setYears(Number(e.target.value))} /></label>
      </form>
      {out ? (
        <>
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th scope="col">Setup</th><th scope="col">Electricity cost (your currency)</th><th scope="col">Carbon</th></tr></thead>
              <tbody>{row("Today", out.today)}{out.best && row("With the best setup", out.best)}</tbody>
            </table>
          </div>
          <p className="hint">Predicted, from the energy figures for your hours, electricity price and grid. {out.excludes}</p>
        </>
      ) : <p className="hint">Run the analysis to see this.</p>}
    </section>
  );
}
