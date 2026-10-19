import { EvidencePanel, RuntimeAndMemory, ThermalNodes } from "./PhysicsSections";
import CoolingOptions from "../components/CoolingOptions";
import ExplorePage from "../pages/ExplorePage";
import type { OptimisationResult, ProjectSpec } from "../types";
import { ENERGY_KEYS, ENERGY_LABEL, Figure, Legend, SERIES, ms, num, useTip } from "./chart";
import { TraceBar, useTrace } from "./TraceBar";
import type { ExecutionTrace } from "./types";

const W = 960;

function fmtTime(s: number) {
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${(s / 60).toFixed(s < 600 ? 1 : 0)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

function Warmup({ t }: { t: ExecutionTrace }) {
  const tip = useTip();
  const th = t.thermal;
  const pts = th.warmup;
  if (!pts.length) return <p className="empty">No warm-up curve for this setup.</p>;
  const H = 300;
  const M = { l: 56, r: 16, t: 14, b: 34 };
  const tMax = pts[pts.length - 1][0] || 1;
  const lo = Math.floor((Math.min(th.ambient_c, pts[0][1]) - 5) / 10) * 10;
  const hi = Math.ceil((Math.max(th.throttle_c, th.unthrottled_c, ...pts.map((p) => p[1])) + 6) / 10) * 10;
  const x = (v: number) => M.l + (v / tMax) * (W - M.l - M.r);
  const y = (v: number) => H - M.b - ((v - lo) / (hi - lo)) * (H - M.t - M.b);
  const d = pts.map(([a, b], i) => `${i ? "L" : "M"}${x(a).toFixed(1)},${y(b).toFixed(1)}`).join(" ");
  const ticks: number[] = [];
  for (let v = lo; v <= hi; v += 10) ticks.push(v);
  function move(e: React.MouseEvent<SVGRectElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const tx = ((e.clientX - r.left) / r.width) * tMax;
    const p = pts.reduce((b, q) => (Math.abs(q[0] - tx) < Math.abs(b[0] - tx) ? q : b), pts[0]);
    tip.show(e, <><strong>{num(p[1])} °C</strong><div>after {fmtTime(p[0])} at constant load</div></>);
  }
  return (
    <div className="viz-box" ref={tip.box}>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Predicted temperature over time under sustained load">
        {ticks.map((v) => (
          <g key={v}><line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} className="grid" /><text x={M.l - 8} y={y(v) + 4} textAnchor="end" className="axis">{v} °C</text></g>
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => <text key={f} x={x(f * tMax)} y={H - 10} textAnchor="middle" className="axis">{fmtTime(f * tMax)}</text>)}
        <line x1={M.l} x2={W - M.r} y1={y(th.ambient_c)} y2={y(th.ambient_c)} className="line-ambient" />
        <text x={W - M.r - 4} y={y(th.ambient_c) - 6} textAnchor="end" className="axis">ambient {num(th.ambient_c)} °C</text>
        <line x1={M.l} x2={W - M.r} y1={y(th.throttle_c)} y2={y(th.throttle_c)} className="line-limit" />
        <text x={M.l + 6} y={y(th.throttle_c) - 6} className="axis axis-bad">throttle point {num(th.throttle_c)} °C</text>
        <path d={d} fill="none" className="line-temp" />
        {th.time_to_throttle_s !== null && th.time_to_throttle_s <= tMax && (
          <g>
            <circle cx={x(th.time_to_throttle_s)} cy={y(th.throttle_c)} r={5} className="dot-bad" />
            <text x={x(th.time_to_throttle_s) + 8} y={y(th.throttle_c) + 16} className="axis">throttles after {fmtTime(th.time_to_throttle_s)}</text>
          </g>
        )}
        <rect x={M.l} y={M.t} width={W - M.l - M.r} height={H - M.t - M.b} fill="transparent" onMouseMove={move} onMouseLeave={tip.hide} />
      </svg>
      {tip.node}
    </div>
  );
}

function HBars({ rows, unit }: { rows: { label: string; value: number; color?: string }[]; unit: string }) {
  const max = Math.max(...rows.map((r) => r.value), 1e-12);
  return (
    <ul className="hbars">
      {rows.map((r) => (
        <li key={r.label}>
          <span className="hb-label">{r.label}</span>
          <span className="hb-track"><span className="hb-bar" style={{ width: `${(100 * r.value) / max}%`, background: r.color ?? "var(--s1)" }} /></span>
          <span className="hb-val num">{num(r.value)} {unit}</span>
        </li>
      ))}
    </ul>
  );
}

export function ThermalPage({ projectId, version, hasBest }: { projectId: number; version: number; hasBest: boolean }) {
  const state = useTrace(projectId, version, hasBest);
  const t = state.data?.trace;
  if (!t) return <div className="twin-page"><TraceBar projectId={projectId} state={state} hasBest={hasBest} /></div>;
  const th = t.thermal;
  const heat = t.components.filter((c) => c.heat_w > 0).sort((a, b) => b.heat_w - a.heat_w);
  return (
    <div className="twin-page">
      <TraceBar projectId={projectId} state={state} hasBest={hasBest} />
      <div className="kpis">
        <div><span>Settles at</span><strong className="num">{num(th.steady_c)} °C</strong><small>{th.throttled ? `held there by throttling (clock ${(th.clock_factor * 100).toFixed(0)}%)` : `${num(th.throttle_c - th.steady_c)} °C below throttling`}</small></div>
        <div><span>Without throttling it would reach</span><strong className="num">{num(th.unthrottled_c)} °C</strong><small>shutdown at {num(th.shutdown_c)} °C</small></div>
        <div><span>Cooling fitted</span><strong className="num">{num(th.r_th_k_per_w)} K/W</strong><small>{th.cooling_name}</small></div>
        <div><span>Cooling needed</span><strong className="num">{th.r_th_needed_k_per_w ? `≤ ${num(th.r_th_needed_k_per_w)} K/W` : "–"}</strong><small>to stay below the throttle point</small></div>
      </div>
      <Figure
        title="Temperature under sustained load"
        note="Predicted warm-up from a cold start at this workload (lumped thermal model)."
        table={<table className="tbl"><thead><tr><th className="num">Time</th><th className="num">°C</th></tr></thead><tbody>{th.warmup.map(([a, b]) => <tr key={a}><td className="num">{fmtTime(a)}</td><td className="num">{num(b)}</td></tr>)}</tbody></table>}
      >
        <Warmup t={t} />
      </Figure>
      <Figure title="Where the heat comes from" note={th.note}>
        <HBars unit="W" rows={heat.map((c) => ({ label: c.name, value: c.heat_w, color: "var(--s2)" }))} />
      </Figure>
      <ThermalNodes projectId={projectId} which={state.which} version={version} />
      <CoolingOptions projectId={projectId} which={state.which} />
    </div>
  );
}

export function EnergyPage({
  projectId,
  version,
  hasBest,
  res,
  spec,
}: {
  projectId: number;
  version: number;
  hasBest: boolean;
  res: OptimisationResult | null;
  spec: ProjectSpec;
}) {
  const state = useTrace(projectId, version, hasBest);
  const t = state.data?.trace;
  const tip = useTip();
  const r = res ? (state.which === "best" && res.best ? res.best : res.baseline) : null;
  return (
    <div className="twin-page">
      <TraceBar projectId={projectId} state={state} hasBest={hasBest} csvTable="events" />
      {t && (
        <>
          <div className="kpis">
            <div><span>Energy per input</span><strong className="num">{num(t.totals.energy_per_inference_mj)} mJ</strong><small>including idle time between inputs</small></div>
            <div><span>Average power</span><strong className="num">{num(t.totals.average_power_w)} W</strong><small>{num(t.totals.active_power_w)} W while computing</small></div>
            {r && <div><span>Electricity</span><strong className="num">{num(r.metrics.cost_per_day.value)} / day</strong><small>at {spec.workload.price_per_kwh} per kWh, {spec.workload.hours_per_day} h/day</small></div>}
            {r && <div><span>Emissions</span><strong className="num">{num(r.metrics.carbon_per_day.value)} kg CO₂e / day</strong><small>at {spec.workload.grid_gco2_per_kwh} g/kWh</small></div>}
          </div>
          <Figure
            title="Energy per input, by cause"
            note="Each operator's energy split by the power model's terms, summed over one batch period and divided by the batch size."
            table={<table className="tbl"><tbody>{ENERGY_KEYS.map((k) => <tr key={k}><td>{ENERGY_LABEL[k]}</td><td className="num">{num(t.energy_per_inference[k])} mJ</td></tr>)}</tbody></table>}
          >
            <Legend items={ENERGY_KEYS.map((k, i) => ({ label: ENERGY_LABEL[k], color: SERIES[i], value: `${num(t.energy_per_inference[k])} mJ` }))} />
            <div className="viz-box" ref={tip.box}>
              <div className="stackbar" role="group" aria-label="Energy per input split by cause">
                {ENERGY_KEYS.map((k, i) => {
                  const total = Object.values(t.energy_per_inference).reduce((a, b) => a + b, 0) || 1;
                  const v = t.energy_per_inference[k];
                  return v > 0 ? (
                    <span key={k} style={{ flex: v / total, background: SERIES[i] }} tabIndex={0}
                      onMouseMove={(e) => tip.show(e, <><strong>{ENERGY_LABEL[k]}</strong><div>{num(v)} mJ ({((100 * v) / total).toFixed(0)}%)</div></>)}
                      onFocus={(e) => tip.show(e, <><strong>{ENERGY_LABEL[k]}</strong><div>{num(v)} mJ</div></>)}
                      onMouseLeave={tip.hide} onBlur={tip.hide} />
                  ) : null;
                })}
              </div>
              {tip.node}
            </div>
          </Figure>
          <Figure title="Energy by stage" note="Which part of the model spends the energy during one batch.">
            <HBars unit="mJ" rows={t.stages.map((s) => ({ label: `${s.index + 1}. ${s.dominant_op} (${ms(s.duration_ms)})`, value: s.energy_mj }))} />
          </Figure>
        </>
      )}
      <RuntimeAndMemory projectId={projectId} which={state.which} version={version} />
      <EvidencePanel projectId={projectId} version={version} />
      {res ? (
        <section className="explore-embed">
          <h2 className="section-title">Every metric, with its range and source</h2>
          <ExplorePage res={res} spec={spec} projectId={projectId} />
        </section>
      ) : (
        <p className="hint">Run the analysis to see every metric with its best-to-worst range, the options the search tried and the co-design comparison.</p>
      )}
    </div>
  );
}
