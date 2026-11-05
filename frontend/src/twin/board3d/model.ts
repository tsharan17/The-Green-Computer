import type { GraphState } from "../../api";
import type { HardwareProfile } from "../../types";
import type { ExecutionTrace } from "../types";

/** What the 3D board shows, built without three.js so the page, its text readout and the 3D view all
 * read the same parts. Positions are 0..1 across the board.
 *
 * Honesty rules, which the page repeats in words:
 * - the peak temperature, each part's watts and every cooling result are the engine's numbers;
 * - the spread of heat around the parts is illustrative (the same diffusion as the 2D board figure);
 * - copper, passives and connectors are an illustration, unless the layout comes from a board file. */

export type PartKind = "compute" | "memory" | "storage" | "link" | "power" | "cooling" | "ic" | "passive";
export type CoolerKind = "none" | "fins" | "fan" | "liquid";

export interface BoardPart {
  id: string;
  name: string;
  kind: PartKind;
  x: number; // centre
  y: number;
  w: number;
  h: number;
  heatW: number;
}

export interface Wire { x0: number; y0: number; x1: number; y1: number; bus: boolean }

export interface BoardSpec {
  label: string;
  parts: BoardPart[];
  wires: Wire[];
  /** Small parts and via positions, drawn only as texture on an illustrative layout. */
  dots: { x: number; y: number; via: boolean }[];
  connectors: { x: number; y: number; w: number; h: number; name: string }[];
  fromBoardFile: boolean;
  cooler: CoolerKind;
  coolerName: string;
  ambientC: number;
  tempC: number | null; // the engine's settled chip temperature; null before an analysis
  throttleC: number;
  mapped: boolean; // has heat figures
}

/** A cooling option's kind, from its catalogue type or its name. */
export function coolerKind(text: string): CoolerKind {
  const s = text.toLowerCase();
  if (/liquid|water|cold.?plate|immersion|aio/.test(s)) return "liquid";
  if (/fan|active|blower|forced|rack|airflow/.test(s)) return "fan";
  if (/sink|passive|fin|vapou?r|spreader/.test(s)) return "fins";
  return "none";
}

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

/** Repeatable pseudo-random numbers, so a device always draws the same way. */
function stream(seed: number) {
  let x = seed || 1;
  return () => {
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    return (x >>> 0) / 4294967296;
  };
}

const inside = (p: BoardPart, x: number, y: number, m = 0.012) =>
  Math.abs(x - p.x) < p.w / 2 + m && Math.abs(y - p.y) < p.h / 2 + m;

/** Copper bundles from the chip to each other part: along, then across. Illustrative routing. */
function route(parts: BoardPart[]): Wire[] {
  const hub = parts.find((p) => p.kind === "compute") ?? parts[0];
  if (!hub) return [];
  const wires: Wire[] = [];
  for (const p of parts) {
    if (p === hub || p.kind === "cooling") continue;
    const bus = p.kind === "memory";
    const n = bus ? 9 : p.kind === "power" ? 5 : 3;
    const pitch = bus ? 0.008 : 0.011;
    for (let i = 0; i < n; i++) {
      const o = (i - (n - 1) / 2) * pitch;
      const corner = hub.y + o;
      wires.push({ x0: hub.x, y0: corner, x1: p.x + o, y1: corner, bus });
      wires.push({ x0: p.x + o, y0: corner, x1: p.x + o, y1: p.y, bus });
    }
  }
  return wires;
}

function texture(parts: BoardPart[], seed: string): BoardSpec["dots"] {
  const r = stream(hash(seed));
  const dots: BoardSpec["dots"] = [];
  for (let i = 0; i < 900 && dots.length < 260; i++) {
    const x = 0.03 + r() * 0.94;
    const y = 0.03 + r() * 0.94;
    if (parts.some((p) => inside(p, x, y))) continue;
    dots.push({ x, y, via: r() < 0.3 });
  }
  return dots;
}

const CONNECTORS: Record<string, BoardSpec["connectors"]> = {
  datacenter_gpu: [{ x: 0.5, y: 0.985, w: 0.8, h: 0.03, name: "PCIe edge" }, { x: 0.93, y: 0.05, w: 0.1, h: 0.06, name: "Power in" }],
  mcu: [{ x: 0.5, y: 0.03, w: 0.5, h: 0.04, name: "Pin header" }, { x: 0.05, y: 0.5, w: 0.07, h: 0.12, name: "USB" }],
  default: [{ x: 0.03, y: 0.3, w: 0.06, h: 0.16, name: "USB" }, { x: 0.03, y: 0.62, w: 0.06, h: 0.2, name: "Ethernet" }, { x: 0.5, y: 0.03, w: 0.6, h: 0.04, name: "Pin header" }],
};

/** A generic set of parts for a device before there is any analysis. */
function previewParts(d: HardwareProfile): BoardPart[] {
  const parts: BoardPart[] = [
    { id: "chip", name: d.name, kind: "compute", x: 0.46, y: 0.46, w: 0.34, h: 0.34, heatW: 0 },
    { id: "mem", name: `Memory, ${d.mem_gb < 1 ? `${Math.round(d.mem_gb * 1024)} MB` : `${d.mem_gb} GB`}`, kind: "memory", x: 0.82, y: 0.34, w: 0.2, h: 0.3, heatW: 0 },
    { id: "power", name: "Power regulators", kind: "power", x: 0.2, y: 0.82, w: 0.3, h: 0.16, heatW: 0 },
  ];
  if (d.kind !== "mcu") parts.push({ id: "link", name: "Host and I/O", kind: "link", x: 0.76, y: 0.8, w: 0.26, h: 0.18, heatW: 0 });
  return parts;
}

function partsFromTrace(t: ExecutionTrace): BoardPart[] {
  return t.components.filter((c) => c.kind !== "cooling").map((c) => ({
    id: c.id, name: c.name, kind: c.kind, x: c.layout.x + c.layout.w / 2, y: c.layout.y + c.layout.h / 2,
    w: Math.max(c.layout.w * 0.86, 0.05), h: Math.max(c.layout.h * 0.86, 0.05), heatW: c.heat_w,
  }));
}

export function boardFromDevice(d: HardwareProfile, label: string, ambientC: number, coolingId: string | null | undefined): BoardSpec {
  const parts = previewParts(d);
  const cool = d.cooling_options.find((c) => c.id === coolingId) ?? d.cooling_options[0];
  return {
    label, parts, wires: route(parts), dots: texture(parts, d.id), connectors: CONNECTORS[d.kind] ?? CONNECTORS.default,
    fromBoardFile: false, cooler: coolerKind(`${cool?.id ?? ""} ${cool?.name ?? ""}`), coolerName: cool?.name ?? "No cooler",
    ambientC, tempC: null, throttleC: d.t_throttle_c ?? 95, mapped: false,
  };
}

export function boardFromTrace(t: ExecutionTrace, label: string, kind: string, deviceClass: string): BoardSpec {
  const parts = partsFromTrace(t);
  return {
    label, parts, wires: route(parts), dots: texture(parts, t.device_id), connectors: CONNECTORS[kind] ?? CONNECTORS.default,
    fromBoardFile: false, cooler: coolerKind(t.thermal.cooling_name), coolerName: t.thermal.cooling_name,
    ambientC: t.thermal.ambient_c, tempC: t.thermal.steady_c, throttleC: t.thermal.throttle_c,
    mapped: parts.some((p) => p.heatW > 0) && deviceClass !== "",
  };
}

/** Real parts and nets from an uploaded board file, or null if the project has none. */
export function boardFromGraph(g: GraphState["graph"], label: string, base: BoardSpec): BoardSpec | null {
  const placed = g.components.filter((c) => c.physical && c.kind !== "board");
  if (placed.length < 2) return null;
  const board = g.components.find((c) => c.kind === "board" && c.physical?.width_mm);
  const xs = placed.map((c) => c.physical!.x_mm);
  const ys = placed.map((c) => c.physical!.y_mm);
  const x0 = board?.physical?.x_mm ?? Math.min(...xs) - 5;
  const y0 = board?.physical?.y_mm ?? Math.min(...ys) - 5;
  const bw = board?.physical?.width_mm ?? Math.max(...xs) - x0 + 5;
  const bh = board?.physical?.height_mm ?? Math.max(...ys) - y0 + 5;
  const span = Math.max(bw, bh);
  const at = new Map(placed.map((c) => [c.id, { x: (c.physical!.x_mm - x0) / span, y: (c.physical!.y_mm - y0) / span }]));
  const parts: BoardPart[] = placed.map((c) => ({
    id: c.id, name: c.name, kind: c.kind === "passive" ? "passive" : "ic", x: at.get(c.id)!.x, y: at.get(c.id)!.y,
    w: c.kind === "passive" ? 0.018 : 0.04, h: c.kind === "passive" ? 0.018 : 0.04, heatW: 0,
  }));
  const wires: Wire[] = g.connections.filter((e) => e.kind === "net" && at.has(e.source) && at.has(e.target)).map((e) => {
    const a = at.get(e.source)!;
    const b = at.get(e.target)!;
    return { x0: a.x, y0: a.y, x1: b.x, y1: b.y, bus: false };
  });
  return { ...base, label, parts, wires, dots: [], connectors: [], fromBoardFile: true, mapped: false, tempC: null };
}

/** Relative heat at each grid point, 0..1, peak at the hottest point. The same idea as the 2D figure:
 * each part's footprint spread by a fixed diffusion length. */
export function heatField(parts: BoardPart[], n: number): Float32Array {
  const out = new Float32Array(n * n);
  const sigma = 0.075;
  const sources = parts.filter((p) => p.heatW > 0);
  let max = 0;
  for (let j = 0; j < n; j++) {
    const y = j / (n - 1);
    for (let i = 0; i < n; i++) {
      const x = i / (n - 1);
      let v = 0;
      for (const p of sources) {
        const dx = Math.max(Math.abs(x - p.x) - p.w / 2, 0);
        const dy = Math.max(Math.abs(y - p.y) - p.h / 2, 0);
        v += (p.heatW / Math.max(p.w * p.h, 0.01)) * Math.exp(-(dx * dx + dy * dy) / (2 * sigma * sigma));
      }
      out[j * n + i] = v;
      if (v > max) max = v;
    }
  }
  if (max > 0) for (let k = 0; k < out.length; k++) out[k] /= max;
  return out;
}

const RAMP: [number, [number, number, number]][] = [
  [0, [0.1, 0.42, 0.45]], [0.3, [0.2, 0.72, 0.42]], [0.55, [0.96, 0.82, 0.3]], [0.78, [0.93, 0.42, 0.14]], [1, [0.62, 0.05, 0.08]],
];

/** Colour for a temperature, 0 = room temperature, 1 = the top of the scale. */
export function heatColor(f: number): [number, number, number] {
  const v = Math.min(Math.max(f, 0), 1);
  for (let i = 1; i < RAMP.length; i++) {
    const [b, cb] = RAMP[i];
    const [a, ca] = RAMP[i - 1];
    if (v <= b) {
      const k = (v - a) / (b - a);
      return [ca[0] + (cb[0] - ca[0]) * k, ca[1] + (cb[1] - ca[1]) * k, ca[2] + (cb[2] - ca[2]) * k];
    }
  }
  return RAMP[RAMP.length - 1][1];
}

/** A worked illustration for the opening page: not any particular board. */
export function demoBoard(): BoardSpec {
  const parts: BoardPart[] = [
    { id: "soc", name: "Chip", kind: "compute", x: 0.46, y: 0.46, w: 0.32, h: 0.32, heatW: 15 },
    { id: "mem", name: "Memory", kind: "memory", x: 0.84, y: 0.32, w: 0.18, h: 0.3, heatW: 2.2 },
    { id: "pwr", name: "Power", kind: "power", x: 0.2, y: 0.84, w: 0.28, h: 0.14, heatW: 1.6 },
    { id: "io", name: "I/O", kind: "link", x: 0.78, y: 0.82, w: 0.24, h: 0.16, heatW: 0.4 },
  ];
  return {
    label: "", parts, wires: route(parts), dots: texture(parts, "demo"), connectors: CONNECTORS.default, fromBoardFile: false,
    cooler: "fan", coolerName: "Fan heatsink", ambientC: 25, tempC: 78, throttleC: 95, mapped: true,
  };
}
