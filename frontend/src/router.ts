import { useEffect, useState } from "react";

/** A tiny hash router: `#/p/12/memory?run=4` -> { parts: ["p","12","memory"], query }.
 * Hash routing keeps deep links working when the FastAPI static server serves index.html. */
export interface Route {
  parts: string[];
  query: URLSearchParams;
}

function parse(): Route {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [path, qs] = raw.split("?");
  return { parts: path.split("/").filter(Boolean), query: new URLSearchParams(qs || "") };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function navigate(to: string) {
  const target = to.startsWith("#") ? to : `#${to.startsWith("/") ? to : `/${to}`}`;
  if (window.location.hash !== target) window.location.hash = target;
}

/** Areas of a project, in the order of the engineering workflow. */
export const AREAS = [
  { id: "input", n: 2, label: "Model and hardware", sub: "Upload, validate, choose" },
  { id: "constraints", n: 3, label: "Constraints and environment", sub: "Requirements, ambient, workload" },
  { id: "system-map", n: 4, label: "System map", sub: "Layers on components" },
  { id: "timeline", n: 5, label: "Execution timeline", sub: "Operator by operator" },
  { id: "memory", n: 6, label: "Memory map", sub: "Tensor lifetimes, peaks" },
  { id: "thermal", n: 7, label: "Thermal and cooling", sub: "Heat over time, cooling options" },
  { id: "energy", n: 8, label: "Energy and performance", sub: "Every metric with its range" },
  { id: "recommendations", n: 9, label: "Recommendations", sub: "Choose changes, compare plans" },
  { id: "verify", n: 10, label: "Verify, history, export", sub: "Measure, track, hand over" },
] as const;

export type AreaId = (typeof AREAS)[number]["id"];
