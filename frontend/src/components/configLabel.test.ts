import { describe, expect, it } from "vitest";
import { configLabel } from "./common";
import type { Config } from "../types";

describe("configLabel", () => {
  it("never shows a raw id with underscores", () => {
    const c = { precision: "int8", batch: 1, power_mode_id: "MAXN", cooling_id: "fan_heatsink", resolution_scale: 1, clock_trim: 1 } as Config;
    const label = configLabel(c);
    expect(label).toContain("fan heatsink");
    expect(label).not.toContain("_");
  });
});
