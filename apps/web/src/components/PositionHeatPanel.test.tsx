import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { init } from "echarts/core";

import { PositionHeatPanel } from "./PositionHeatPanel";
import type { AnalysisResponse } from "../types";

const analysis: AnalysisResponse = {
  targetIssue: "next",
  modelVersion: "m",
  snapshotHash: "x",
  seedHint: 1,
  positionProbabilities: {
    front: [
      {
        position: 1,
        top_numbers: [{ number: 1, raw_score: 0, calibrated_prob: 0.1, top_factors: [] }],
      },
    ],
    back: [
      {
        position: 1,
        top_numbers: [{ number: 1, raw_score: 0, calibrated_prob: 0.2, top_factors: [] }],
      },
    ],
  },
  featureSummary: {},
  structureBreakdown: {},
  notes: "",
};

describe("PositionHeatPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("skips chart in jsdom", () => {
    render(<PositionHeatPanel analysis={analysis} />);
    expect(screen.getByText(/测试环境跳过图表渲染/)).toBeInTheDocument();
  });

  it("runs chart lifecycle when UA is not jsdom (stubbed echarts init)", async () => {
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 Chrome/120.0" });
    render(<PositionHeatPanel analysis={analysis} />);
    await waitFor(() => expect(vi.mocked(init)).toHaveBeenCalled());
  });
});
