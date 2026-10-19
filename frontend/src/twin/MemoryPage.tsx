import { useState } from "react";
import { Figure, Legend, bytes, ms, useTip } from "./chart";
import { TraceBar, useTrace } from "./TraceBar";
import type { ExecutionTrace } from "./types";

const W = 960;

function MemoryArea({ t, fit }: { t: ExecutionTrace; fit: boolean }) {
  const tip = useTip();
  const pts = t.memory_timeline;
  const H = 300;
  const M = { l: 70, r: 16, t: 14, b: 30 };
  const endT = t.totals.batch_ms || 1;
  const cap = pts[0]?.capacity_bytes ?? 0;
  const used = Math.max(...pts.map((p) => p.total_bytes));
  const top = (fit ? used * 1.15 : Math.max(cap, used) * 1.08) || 1;
  const capOnScale = cap > 0 && cap <= top;
  const x = (v: number) => M.l + (v / endT) * (W - M.l - M.r);
  const y = (v: number) => H - M.b - (v / top) * (H - M.t - M.b);
  const ends = pts.map((_p, i) => (i + 1 < pts.length ? pts[i + 1].t_ms : endT));
  const band = (lo: (i: number) => number, hi: (i: number) => number) => {
    const upper = pts.flatMap((p, i) => [`${x(p.t_ms)},${y(hi(i))}`, `${x(ends[i])},${y(hi(i))}`]);
    const lower = pts.flatMap((p, i) => [`${x(p.t_ms)},${y(lo(i))}`, `${x(ends[i])},${y(lo(i))}`]).reverse();
    return `M${upper.join(" L")} L${lower.join(" L")} Z`;
  };
  const w = (i: number) => pts[i].weights_bytes;
  const wr = (i: number) => w(i) + pts[i].runtime_bytes;
  const all = (i: number) => wr(i) + pts[i].activation_bytes;
  const peakI = pts.reduce((b, p, i) => (p.total_bytes > pts[b].total_bytes ? i : b), 0);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);

  function move(e: React.MouseEvent<SVGRectElement>) {
    const r = (e.currentTarget as SVGRectElement).getBoundingClientRect();
    const tx = ((e.clientX - r.left) / r.width) * endT;
    const i = Math.max(0, pts.findIndex((p, k) => tx >= p.t_ms && tx < ends[k]));
    const p = pts[i];
    const ev = t.events[p.event];
    tip.show(e, (
      <>
        <strong>{ev?.name}</strong> <span className="muted">at {ms(p.t_ms)}</span>
        <div>Activations {bytes(p.activation_bytes)}</div>
        <div>Weights {bytes(p.weights_bytes)}, runtime {bytes(p.runtime_bytes)}</div>
        <div>Total {bytes(p.total_bytes)} of {bytes(p.capacity_bytes)}</div>
      </>
    ));
  }

  return (
    <div className="viz-box" ref={tip.box}>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Memory in use over the batch">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} className="grid" />
            <text x={M.l - 8} y={y(v) + 4} textAnchor="end" className="axis">{bytes(v)}</text>
          </g>
        ))}
        <path d={band(() => 0, w)} style={{ fill: "var(--s1)" }} />
        <path d={band(w, wr)} style={{ fill: "var(--s2)" }} />
        <path d={band(wr, all)} style={{ fill: "var(--s3)" }} />
        {cap > 0 && !capOnScale && (
          <text x={W - M.r - 4} y={M.t + 10} textAnchor="end" className="axis">usable capacity {bytes(cap)} is above this scale ({(cap / used).toFixed(1)}× the peak)</text>
        )}
        {capOnScale && (
          <g>
            <line x1={M.l} x2={W - M.r} y1={y(cap)} y2={y(cap)} className="line-limit" />
            <text x={W - M.r - 4} y={y(cap) - 6} textAnchor="end" className="axis axis-bad">usable capacity {bytes(cap)}</text>
          </g>
        )}
        <circle cx={(x(pts[peakI].t_ms) + x(ends[peakI])) / 2} cy={y(pts[peakI].total_bytes)} r={5} className="viz-peak" />
        <text x={(x(pts[peakI].t_ms) + x(ends[peakI])) / 2 + 8} y={y(pts[peakI].total_bytes) - 8} className="axis">peak {bytes(pts[peakI].total_bytes)}</text>
        {[0, 0.5, 1].map((f) => (
          <text key={f} x={x(f * endT)} y={H - 8} textAnchor="middle" className="axis">{ms(f * endT)}</text>
        ))}
        <rect x={M.l} y={M.t} width={W - M.l - M.r} height={H - M.t - M.b} fill="transparent" onMouseMove={move} onMouseLeave={tip.hide} />
      </svg>
      {tip.node}
    </div>
  );
}

function Lifetimes({ t }: { t: ExecutionTrace }) {
  const tip = useTip();
  const n = t.events.filter((e) => e.kind !== "idle").length;
  const tensors = [...t.tensors].sort((a, b) => b.bytes - a.bytes).slice(0, 36).sort((a, b) => a.producer - b.producer);
  const rowH = 12;
  const L = 16;
  const H = tensors.length * rowH + 30;
  const x = (i: number) => L + ((i + 1) / (n + 1)) * (W - L - 16);
  const maxB = Math.max(...tensors.map((s) => s.bytes), 1);
  return (
    <div className="viz-box" ref={tip.box}>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="group" aria-label="Tensor lifetimes">
        {tensors.map((s, k) => {
          const x1 = x(s.producer);
          const x2 = x(Math.min(s.last_use, n));
          const h = 3 + (rowH - 5) * Math.sqrt(s.bytes / maxB);
          return (
            <rect key={s.id} x={x1} y={6 + k * rowH + (rowH - h) / 2} width={Math.max(2, x2 - x1)} height={h} rx={2}
              style={{ fill: s.kind === "activation" ? "var(--s3)" : s.kind === "input" ? "var(--s1)" : "var(--s5)" }}
              tabIndex={0}
              onMouseMove={(e) => tip.show(e, <><strong>{s.id}</strong><div>{bytes(s.bytes)} ({s.kind})</div><div>alive from operator {s.producer < 0 ? "start" : s.producer} to {s.last_use >= n ? "end" : s.last_use}</div></>)}
              onFocus={(e) => tip.show(e, <><strong>{s.id}</strong><div>{bytes(s.bytes)}</div></>)}
              onMouseLeave={tip.hide}
              onBlur={tip.hide}
            />
          );
        })}
        <text x={L} y={H - 6} className="axis">first operator</text>
        <text x={W - 16} y={H - 6} textAnchor="end" className="axis">last operator</text>
      </svg>
      {tip.node}
    </div>
  );
}

function Pressure({ t }: { t: ExecutionTrace }) {
  const tip = useTip();
  const ops = t.events.filter((e) => e.kind !== "idle");
  const H = 120;
  const M = { l: 70, b: 18, t: 10 };
  const bw = (W - M.l - 16) / Math.max(ops.length, 1);
  const top = Math.max(1, ...ops.map((e) => e.bandwidth_utilisation));
  const y = (v: number) => H - M.b - (v / top) * (H - M.t - M.b);
  return (
    <div className="viz-box" ref={tip.box}>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Memory bandwidth used by each operator">
        <line x1={M.l} x2={W - 16} y1={y(1)} y2={y(1)} className="line-limit" />
        <text x={M.l - 8} y={y(1) + 4} textAnchor="end" className="axis">100%</text>
        <text x={M.l - 8} y={y(0) + 4} textAnchor="end" className="axis">0%</text>
        {ops.map((e, i) => (
          <rect key={e.index} x={M.l + i * bw + 1} y={y(e.bandwidth_utilisation)} width={Math.max(1, bw - 2)} height={y(0) - y(e.bandwidth_utilisation)}
            rx={Math.min(2, bw / 4)} style={{ fill: "var(--s2)" }}
            onMouseMove={(m) => tip.show(m, <><strong>{e.name}</strong><div>{(e.bandwidth_utilisation * 100).toFixed(0)}% of the memory path ({e.bandwidth_gbs.toPrecision(3)} GB/s)</div></>)}
            onMouseLeave={tip.hide} />
        ))}
      </svg>
      {tip.node}
    </div>
  );
}

export default function MemoryPage({ projectId, version, hasBest }: { projectId: number; version: number; hasBest: boolean }) {
  const state = useTrace(projectId, version, hasBest);
  const t = state.data?.trace;
  const [fit, setFit] = useState(true);
  if (!t) return <div className="twin-page"><TraceBar projectId={projectId} state={state} hasBest={hasBest} csvTable="memory" /></div>;
  const tot = t.totals;
  const fits = tot.peak_working_memory_bytes <= tot.memory_capacity_bytes;
  return (
    <div className="twin-page">
      <TraceBar projectId={projectId} state={state} hasBest={hasBest} csvTable="memory" />
      <div className="kpis">
        <div><span>Peak working memory</span><strong className="num">{bytes(tot.peak_working_memory_bytes)}</strong><small>{fits ? "fits" : "exceeds"} {bytes(tot.memory_capacity_bytes)} usable</small></div>
        <div><span>Weights</span><strong className="num">{bytes(tot.weights_bytes)}</strong><small>{t.components.some((c) => c.id === "flash") ? "kept in flash" : "resident in memory"}</small></div>
        <div><span>Fit check used</span><strong className="num">{bytes(tot.analysis_memory_bytes)}</strong><small>the engine's conservative estimate</small></div>
      </div>
      {!fits && <p className="error" role="alert">At its peak this setup needs more memory than the device can use. See the recommendations for smaller precisions or batches.</p>}
      <Figure
        title="Memory over the batch"
        actions={
          <div className="seg" role="radiogroup" aria-label="Vertical scale">
            <button role="radio" aria-checked={fit} className={fit ? "on" : ""} onClick={() => setFit(true)}>Fit to usage</button>
            <button role="radio" aria-checked={!fit} className={!fit ? "on" : ""} onClick={() => setFit(false)}>Show capacity</button>
          </div>
        }
        note={t.fidelity === "graph" ? "Activations follow tensor lifetimes from the graph: allocated by their producer, freed after their last reader." : t.fidelity_note}
        table={
          <table className="tbl">
            <thead><tr><th>Operator</th><th className="num">Time</th><th className="num">Weights</th><th className="num">Runtime</th><th className="num">Activations</th><th className="num">Total</th></tr></thead>
            <tbody>{t.memory_timeline.map((p) => (
              <tr key={p.event}><td>{t.events[p.event]?.name}</td><td className="num">{ms(p.t_ms)}</td><td className="num">{bytes(p.weights_bytes)}</td><td className="num">{bytes(p.runtime_bytes)}</td><td className="num">{bytes(p.activation_bytes)}</td><td className="num">{bytes(p.total_bytes)}</td></tr>
            ))}</tbody>
          </table>
        }
      >
        <Legend items={[
          { label: "Weights", color: "var(--s1)" },
          { label: "Runtime and buffers", color: "var(--s2)" },
          { label: "Live activations", color: "var(--s3)" },
        ]} />
        <MemoryArea t={t} fit={fit} />
      </Figure>
      {t.tensors.length > 0 && (
        <Figure title="Tensor lifetimes" note="The largest tensors, from the operator that writes them to the last one that reads them. Thicker = bigger.">
          <Legend items={[{ label: "Model input", color: "var(--s1)" }, { label: "Activation", color: "var(--s3)" }, { label: "Model output", color: "var(--s5)" }]} />
          <Lifetimes t={t} />
        </Figure>
      )}
      <Figure title="Bandwidth pressure" note="Share of the memory path's bandwidth each operator uses. Bars near 100% are memory-bound.">
        <Pressure t={t} />
      </Figure>
    </div>
  );
}
