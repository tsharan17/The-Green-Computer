import { describe, expect, it } from "vitest";
import { coolerKind, demoBoard, heatColor, heatField } from "./model";

describe("3D board model", () => {
  it("reads the cooler type from its name", () => {
    expect(coolerKind("Heatsink with fan")).toBe("fan");
    expect(coolerKind("Passive heatsink")).toBe("fins");
    expect(coolerKind("Liquid cold plate")).toBe("liquid");
  });

  it("the hottest point of the map is at the part that makes the most heat", () => {
    const { parts } = demoBoard();
    const hot = [...parts].sort((a, b) => b.heatW - a.heatW)[0];
    expect(hot.heatW).toBeGreaterThan(0);
    const n = 64;
    const f = heatField(parts, n);
    const peak = f.indexOf(Math.max(...f));
    const x = (peak % n) / (n - 1);
    const y = Math.floor(peak / n) / (n - 1);
    expect(Math.abs(x - hot.x)).toBeLessThanOrEqual(hot.w / 2 + 1 / n);
    expect(Math.abs(y - hot.y)).toBeLessThanOrEqual(hot.h / 2 + 1 / n);
    expect(Math.max(...f)).toBe(1);
  });

  it("a board with no heat has a flat map, not an invented one", () => {
    const f = heatField([], 8);
    expect(Math.max(...f)).toBe(0);
  });

  it("colours stay valid at and beyond the ends of the scale", () => {
    for (const t of [-1, 0, 0.5, 1, 2]) for (const c of heatColor(t)) {
      expect(c).toBeGreaterThanOrEqual(0);
      expect(c).toBeLessThanOrEqual(1);
    }
  });
});
