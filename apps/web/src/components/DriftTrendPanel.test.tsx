import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { init } from "echarts/core";

import { DriftTrendPanel } from "./DriftTrendPanel";
import type { PredictionRun } from "../types";

describe("DriftTrendPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows empty hint without drift", () => {
    const runs: PredictionRun[] = [
      {
        run_id: "r1",
        target_issue: "next",
        model_version: "m",
        seed: 1,
        created_at: "t",
        plan1: [],
        plan2: [],
      },
    ];
    render(<DriftTrendPanel runs={runs} />);
    expect(screen.getByText(/暂无漂移序列/)).toBeInTheDocument();
  });

  it("runs chart lifecycle when drift exists and UA is not jsdom", async () => {
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 Chrome/120.0" });
    const drift = {
      drift_score: 0.12,
      position_delta: 0.1,
      set_delta: 0.1,
      structure_delta: 0.1,
      score_delta: 0.1,
      overlap_delta: 0.1,
    };
    const runs: PredictionRun[] = [
      {
        run_id: "r1",
        target_issue: "next",
        model_version: "m",
        seed: 1,
        created_at: "t",
        plan1: [],
        plan2: [],
        drift,
      },
    ];
    render(<DriftTrendPanel runs={runs} />);
    await waitFor(() => expect(vi.mocked(init)).toHaveBeenCalled());
    expect(document.querySelector(".drift-chart")).toBeTruthy();
  });
});
