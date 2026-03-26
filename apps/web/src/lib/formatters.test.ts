import { describe, expect, it } from "vitest";

import {
  driftLevelFromScore,
  driftLevelLabel,
  formatBall,
  formatTicketLine,
  postmortemStatus,
  summarizeDrift,
} from "./formatters";
import type { DriftReport, PostmortemSummary, Ticket } from "../types";

describe("formatters", () => {
  it("formatBall pads zeros", () => {
    expect(formatBall(3)).toBe("03");
    expect(formatBall(35)).toBe("35");
  });

  it("formatTicketLine joins zones", () => {
    const t: Ticket = { front: [1, 2, 3, 4, 5], back: [6, 7], score: 0, tags: [] };
    expect(formatTicketLine(t)).toBe("01 02 03 04 05 + 06 07");
  });

  it("driftLevelFromScore buckets", () => {
    expect(driftLevelFromScore(undefined)).toBe("unknown");
    expect(driftLevelFromScore(0.1)).toBe("low");
    expect(driftLevelFromScore(0.2)).toBe("medium");
    expect(driftLevelFromScore(0.5)).toBe("high");
  });

  it("driftLevelLabel maps", () => {
    expect(driftLevelLabel("low")).toBe("低");
    expect(driftLevelLabel("unknown")).toBe("—");
  });

  it("postmortemStatus detects pending", () => {
    expect(postmortemStatus(null)).toBe("pending");
    const p: PostmortemSummary = {
      issue: "1",
      model_version: "m",
      hit_summary: "pending draw",
      weighted_return: 0,
      created_at: "t",
    };
    expect(postmortemStatus(p)).toBe("pending");
    const p2: PostmortemSummary = { ...p, hit_summary: "5+2 hit" };
    expect(postmortemStatus(p2)).toBe("recorded");
  });

  it("summarizeDrift handles null and values", () => {
    expect(summarizeDrift(null)).toContain("暂无");
    const d: DriftReport = {
      drift_score: 0.2,
      position_delta: 0.1,
      set_delta: 0.05,
      structure_delta: 0,
      score_delta: 0,
      overlap_delta: 0,
    };
    expect(summarizeDrift(d)).toContain("0.200");
  });
});
