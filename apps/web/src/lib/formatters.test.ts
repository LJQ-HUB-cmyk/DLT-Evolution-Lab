import { describe, expect, it } from "vitest";

import {
  driftLevelFromBackend,
  driftLevelFromScore,
  driftLevelLabel,
  summarizeDrift,
} from "./formatters";
import type { DriftReport } from "../types";

describe("formatters M7", () => {
  it("maps drift levels to Chinese labels", () => {
    expect(driftLevelLabel(driftLevelFromScore(0.1))).toBe("低");
    expect(driftLevelLabel(driftLevelFromScore(0.2))).toBe("中");
    expect(driftLevelLabel(driftLevelFromScore(0.9))).toBe("高");
    expect(driftLevelLabel("unknown")).toBe("--");
  });

  it("maps backend NORMAL/WARN/CRITICAL", () => {
    expect(driftLevelLabel(driftLevelFromBackend("NORMAL"))).toBe("低");
    expect(driftLevelLabel(driftLevelFromBackend("WARN"))).toBe("中");
    expect(driftLevelLabel(driftLevelFromBackend("CRITICAL"))).toBe("高");
  });

  it("summarizeDrift uses Chinese empty state", () => {
    expect(summarizeDrift(null)).toBe("暂无漂移数据");
    const d: DriftReport = {
      drift_score: 0.2,
      position_dist_drift: 0.1,
      number_set_drift: 0.05,
    };
    expect(summarizeDrift(d)).toContain("综合分");
  });
});
