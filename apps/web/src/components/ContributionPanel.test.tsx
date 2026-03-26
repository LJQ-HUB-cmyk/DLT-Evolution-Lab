import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ContributionPanel } from "./ContributionPanel";
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
        top_numbers: [
          {
            number: 7,
            raw_score: 1,
            calibrated_prob: 0.33,
            top_factors: [{ freq_10: 0.2 }],
          },
        ],
      },
    ],
    back: [],
  },
  featureSummary: {},
  structureBreakdown: {},
  notes: "",
};

describe("ContributionPanel", () => {
  it("renders top factor", () => {
    render(<ContributionPanel analysis={analysis} />);
    expect(screen.getByText(/freq_10/)).toBeInTheDocument();
  });
});
