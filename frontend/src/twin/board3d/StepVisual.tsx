import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { type GraphState, plans, systemGraph, twin } from "../../api";
import { useBaselineTrace } from "../KeyFigures";
import { num } from "../chart";
import { type Camera, type Palette, readPalette } from "../map3d/palette";
import type { StoredTrace } from "../types";
import type { CoolingRow, HardwareProfile, OptimisationResult, ProjectSpec } from "../../types";
import { type BoardSpec, boardFromDevice, boardFromGraph, boardFromTrace, coolerKind } from "./model";
import "./board3d.css";

const Board3DView = lazy(() => import("./Board3DView"));

export function hasWebGL() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function reducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

type Mode = "hardware" | "limits" | "thermal" | "compare" | "cooling" | "verify" | "memory" | "activity";

/** What the 3D view shows at each step of the path. */
const VIEWS: Record<string, { mode: Mode; title: string; say: string }> = {
  input: { mode: "hardware", title: "Your hardware", say: "The board you picked, taken apart: chip, memory, power, copper and cooler." },
  constraints: { mode: "limits", title: "Your board and its heat limit", say: "The red plane is where the chip starts slowing itself down." },
  check: { mode: "hardware", title: "The hardware being checked", say: "What the analysis will model." },
  summary: { mode: "thermal", title: "Where the heat sits today", say: "Height and colour both show temperature, above the hardware that makes it." },
  engine: { mode: "compare", title: "Today and with the recommended plan", say: "Same scale, side by side." },
  results: { mode: "compare", title: "Today and with the recommended plan", say: "Same scale, side by side." },
  catalogue: { mode: "compare", title: "Today and with the recommended plan", say: "Same scale, side by side." },
  plan: { mode: "compare", title: "Today and with the recommended plan", say: "Same scale, side by side." },
  saved: { mode: "compare", title: "Today and with the recommended plan", say: "Same scale, side by side." },
  cooling: { mode: "cooling", title: "What each cooler does to the heat", say: "Pick a cooler. Each temperature is solved by the engine for this workload." },
  thermal: { mode: "cooling", title: "What each cooler does to the heat", say: "Pick a cooler. Each temperature is solved by the engine for this workload." },
  energy: { mode: "thermal", title: "Where the power turns into heat", say: "Each part's watts are labelled on the board." },
  memory: { mode: "memory", title: "Memory and its path to the chip", say: "Memory parts and the copper bus to the chip." },
  timeline: { mode: "activity", title: "The hardware at work", say: "Parts light up as each step of one batch uses them." },
  run: { mode: "verify", title: "The setup you are about to measure", say: "A real run replaces predictions with measured numbers, labelled as such." },
  measured: { mode: "verify", title: "The setup behind these results", say: "This view shows the trace named below, predicted or measured." },
  export: { mode: "thermal", title: "The setup in this report", say: "Today's setup, as the report describes it." },
};

const HOME: Camera = { azimuth: 0.62, elevation: 0.62, distance: 2.05 };
const FAR: Camera = { azimuth: 0.1, elevation: 0.74, distance: 2.5 };

function remembered(): boolean {
  try {
    return localStorage.getItem("gc-3d-hidden") === "1";
  } catch {
    return false;
  }
}

function useBestTrace(projectId: number, version: number, runKey: number | null, on: boolean) {
  const [t, setT] = useState<StoredTrace | null>(null);
  useEffect(() => {
    if (!on) return;
    let live = true;
    twin.create(projectId, "best").then((x) => live && setT(x)).catch(() => live && setT(null));
    return () => { live = false; };
  }, [projectId, version, runKey, on]);
  return on ? t : null;
}

/** The 3D view for one step of the path. Text beside it always carries the same facts. */
export default function StepVisual({ step, projectId, version, runId, res, spec, device }: {
  step: string; projectId: number; version: number; runId: number | null; res: OptimisationResult | null; spec: ProjectSpec; device: HardwareProfile | undefined;
}) {
  const view = VIEWS[step];
  const [hidden, setHidden] = useState(remembered);
  if (!view || !device) return null;
  return (
    <section className={`step3d ${hidden ? "folded" : ""}`} aria-label={view.title}>
      <div className="s3-head">
        <div>
          <h2>{view.title}</h2>
          {!hidden && <p className="hint">{view.say}</p>}
        </div>
        <button className="link" aria-expanded={!hidden} onClick={() => {
          setHidden(!hidden);
          try { localStorage.setItem("gc-3d-hidden", hidden ? "0" : "1"); } catch { /* the choice just isn't remembered */ }
        }}>{hidden ? "Show the 3D view" : "Hide the 3D view"}</button>
      </div>
      {!hidden && <Stage key={view.mode} mode={view.mode} projectId={projectId} version={version} runId={runId} res={res} spec={spec} device={device} />}
    </section>
  );
}

function Stage({ mode, projectId, version, runId, res, spec, device }: {
  mode: Mode; projectId: number; version: number; runId: number | null; res: OptimisationResult | null; spec: ProjectSpec; device: HardwareProfile;
}) {
  const analysed = !!res && mode !== "hardware";
  const trace = useBaselineTrace(projectId, version, runId, analysed).data;
  const best = useBestTrace(projectId, version, runId, mode === "compare" && !!res?.best);
  const [graph, setGraph] = useState<GraphState | null>(null);
  const [rows, setRows] = useState<CoolingRow[] | null>(null);
  const [pick, setPick] = useState<string>("current");
  const [cam, setCam] = useState<Camera>(mode === "compare" ? FAR : HOME);
  const [explode, setExplode] = useState(mode === "hardware" ? 0.45 : 0);
  const [showHeat, setShowHeat] = useState(true);
  const [showCircuit, setShowCircuit] = useState(true);
  const [webgl] = useState(hasWebGL);
  const [motion] = useState(() => !reducedMotion());
  const [visible, setVisible] = useState(true);
  const [pal] = useState<Palette>(readPalette);
  const [tick, setTick] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; cam: Camera } | null>(null);

  useEffect(() => {
    if (mode === "hardware" || mode === "limits") systemGraph.current(projectId).then(setGraph).catch(() => setGraph(null));
  }, [mode, projectId, version]);
  useEffect(() => {
    if (mode === "cooling") plans.cooling(projectId, "baseline").then((d) => setRows(d.rows)).catch(() => setRows(null));
  }, [mode, projectId, version]);
  // Pause the animation when the view is scrolled away.
  useEffect(() => {
    if (!box.current || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting));
    io.observe(box.current);
    return () => io.disconnect();
  }, []);

  const t = analysed ? trace?.trace ?? null : null;
  const events = useMemo(() => t?.events ?? [], [t]);
  useEffect(() => {
    if (mode !== "activity" || !motion || !visible || !events.length) return;
    const id = window.setInterval(() => setTick((i) => i + 1), 700);
    return () => window.clearInterval(id);
  }, [mode, motion, visible, events.length]);

  const cooled = rows?.find((r) => r.id === pick) ?? null;
  const preview = useMemo(() => boardFromDevice(device, "", spec.workload.ambient_c, spec.cooling_id), [device, spec.workload.ambient_c, spec.cooling_id]);
  const boards: BoardSpec[] = useMemo(() => {
    if (t) {
      const today = boardFromTrace(t, mode === "compare" && best ? "Today" : "", device.kind, device.kind);
      if (mode === "compare" && best) return [today, boardFromTrace(best.trace, "With the plan", device.kind, device.kind)];
      if (mode === "cooling" && cooled && cooled.id !== "current") return [{ ...today, cooler: coolerKind(`${cooled.type} ${cooled.name}`), coolerName: cooled.name }];
      if (mode === "limits") return [today];
      return [today];
    }
    const real = graph?.graph ? boardFromGraph(graph.graph, "", preview) : null;
    return [real ?? preview];
  }, [t, best, mode, cooled, device.kind, graph, preview]);

  const temps = boards.map((b, i) => (mode === "cooling" && cooled ? cooled.temperature_c : i === 1 ? best?.trace.thermal.steady_c ?? null : b.tempC));
  const scaleMax = Math.max(boards[0].throttleC + 8, ...temps.filter((x): x is number => x !== null), ...(rows ?? []).map((r) => r.temperature_c));
  const activeIds = useMemo(() => new Set(mode === "activity" && events.length ? events[tick % events.length].components : []), [mode, events, tick]);
  const glowKinds = useMemo(() => new Set(mode === "memory" ? ["memory"] : []), [mode]);
  const heatOn = showHeat && mode !== "hardware" && mode !== "memory" && mode !== "activity";
  const animate = motion && visible;
  const b0 = boards[0];
  const rotate = (da: number, de = 0) => setCam((c) => ({ ...c, azimuth: c.azimuth + da, elevation: Math.min(1.45, Math.max(0.08, c.elevation + de)) }));
  const zoom = (f: number) => setCam((c) => ({ ...c, distance: Math.min(4, Math.max(0.9, c.distance * f)) }));
  const running = mode === "activity" && events.length ? events[tick % events.length] : null;
  const words = `${device.name}: ${b0.parts.length} parts, ${b0.coolerName}. ${temps[0] !== null ? `Chip settles at ${num(temps[0])} °C, slows down at ${num(b0.throttleC)} °C.` : "No heat figures until the analysis has run."}`;

  return (
    <div className="s3-body">
      {webgl ? (
        <div className={`s3-canvas ${boards.length > 1 ? "wide" : ""}`} ref={box} tabIndex={0} role="group" aria-roledescription="3D view" aria-label={`${words} Drag or use the arrow keys to turn it, plus and minus to zoom.`}
          onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, cam }; }}
          onPointerMove={(e) => {
            const d = drag.current;
            if (!d || e.buttons === 0) return;
            setCam({ ...d.cam, azimuth: d.cam.azimuth - (e.clientX - d.x) * 0.008, elevation: Math.min(1.45, Math.max(0.08, d.cam.elevation + (e.clientY - d.y) * 0.006)) });
          }}
          onPointerUp={() => { drag.current = null; }}
          onKeyDown={(e) => {
            const k: Record<string, () => void> = { ArrowLeft: () => rotate(0.12), ArrowRight: () => rotate(-0.12), ArrowUp: () => rotate(0, 0.08), ArrowDown: () => rotate(0, -0.08), "+": () => zoom(0.9), "=": () => zoom(0.9), "-": () => zoom(1.1), "0": () => setCam(HOME) };
            if (k[e.key]) { e.preventDefault(); k[e.key](); }
          }}>
          <Suspense fallback={<div className="skeleton" aria-busy="true"><div className="sk-line w60" /></div>}>
            <Board3DView boards={boards} temps={temps} scaleMaxC={scaleMax} cam={cam} pal={pal} animate={animate} explode={explode} showHeat={heatOn} showCircuit={showCircuit}
              showFlow={mode === "cooling" || mode === "thermal" || mode === "compare"} showLabels={boards.length === 1} limit={mode === "limits"} activeIds={activeIds} glowKinds={glowKinds} />
          </Suspense>
          <div className="s3-view-buttons" role="group" aria-label="Turn and zoom">
            <button onClick={() => rotate(0.3)} aria-label="Turn left">⟲</button>
            <button onClick={() => rotate(-0.3)} aria-label="Turn right">⟳</button>
            <button onClick={() => zoom(0.85)} aria-label="Zoom in">+</button>
            <button onClick={() => zoom(1.15)} aria-label="Zoom out">−</button>
          </div>
        </div>
      ) : (
        <p className="note" role="status">This browser cannot draw 3D (WebGL is off or unavailable). {words}</p>
      )}

      <div className="s3-side">
        {mode === "cooling" && rows && (
          <label className="s3-field">Cooling
            <select value={pick} onChange={(e) => setPick(e.target.value)}>
              {rows.map((r) => <option key={r.id} value={r.id}>{r.id === "current" ? `${r.name} (fitted now)` : r.name}: {num(r.temperature_c)} °C</option>)}
            </select>
          </label>
        )}
        {mode === "cooling" && !rows && <p className="hint">Loading the cooling options…</p>}
        <dl className="kv s3-facts">
          {boards.length > 1 ? (
            <>
              <dt>Today</dt><dd className="num">{temps[0] !== null ? `${num(temps[0])} °C` : "–"}, {boards[0].coolerName}</dd>
              <dt>With the plan</dt><dd className="num">{temps[1] !== null ? `${num(temps[1]!)} °C` : "–"}, {boards[1].coolerName}</dd>
            </>
          ) : (
            <>
              {temps[0] !== null && <><dt>Chip settles at</dt><dd className="num">{num(temps[0])} °C</dd></>}
              <dt>Slows down at</dt><dd className="num">{num(b0.throttleC)} °C</dd>
              <dt>Room</dt><dd className="num">{num(b0.ambientC)} °C</dd>
              <dt>Cooling</dt><dd>{b0.coolerName}</dd>
            </>
          )}
          {cooled && <><dt>Clock after any slowing</dt><dd className="num">{(cooled.clock_factor * 100).toFixed(0)}%</dd><dt>Power</dt><dd className="num">{num(cooled.power_w)} W</dd></>}
          {running && <><dt>Running now</dt><dd>{running.name}</dd></>}
          {t && <><dt>Source</dt><dd>{t.kind === "measured" ? "measured trace" : `predicted (${t.provenance})`}</dd></>}
        </dl>
        <div className="s3-controls">
          {(mode === "hardware" || mode === "memory" || mode === "activity") && (
            <label className="s3-field">Take apart
              <input type="range" min={0} max={1} step={0.01} value={explode} onChange={(e) => setExplode(Number(e.target.value))} />
            </label>
          )}
          {!["hardware", "memory", "activity"].includes(mode) && t && (
            <label className="check-row"><input type="checkbox" checked={showHeat} onChange={(e) => setShowHeat(e.target.checked)} /> Heat map</label>
          )}
          <label className="check-row"><input type="checkbox" checked={showCircuit} onChange={(e) => setShowCircuit(e.target.checked)} /> Copper and small parts</label>
        </div>
        {heatOn && temps[0] !== null && <div className="s3-scale" aria-hidden><span>{num(b0.ambientC)} °C</span><i /><span>{num(scaleMax)} °C</span></div>}
        <p className="hint s3-honest">
          {b0.fromBoardFile
            ? "Parts and connections are placed from your board file. Heat is not mapped onto them, because the engine models the chip and memory as a whole."
            : "Illustrative layout, not your board's real circuit: upload a KiCad board to see its real parts and nets. "}
          {t && "The peak temperature, each part's watts and the cooling results are the engine's numbers; the spread of heat between parts is illustrative, not a CFD solve. Moving air shows the kind of cooling, not a flow simulation."}
        </p>
        {t && (
          <details className="s3-parts">
            <summary>Every part, as a table</summary>
            <table className="tbl"><thead><tr><th>Part</th><th className="num">Heat</th></tr></thead>
              <tbody>{t.components.filter((c) => c.kind !== "cooling").map((c) => <tr key={c.id}><td>{c.name}</td><td className="num">{num(c.heat_w)} W</td></tr>)}</tbody>
            </table>
          </details>
        )}
      </div>
    </div>
  );
}
