import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModelMetaPanel } from "./ModelMetaPanel";
import type { AnalysisResponse, ModelRegistryItem } from "../types";

const analysis: AnalysisResponse = {
  targetIssue: "next",
  modelVersion: "mv-1",
  snapshotHash: "ab",
  seedHint: 42,
  positionProbabilities: { front: [], back: [] },
  featureSummary: {},
  structureBreakdown: {},
  notes: "",
};

const champion: ModelRegistryItem = { version: "mv-1", status: "champion", credit_score: 72.3 };

describe("ModelMetaPanel", () => {
  it("renders champion credit and drift pill", () => {
    render(
      <ModelMetaPanel
        analysis={analysis}
        loading={false}
        champion={champion}
        latestDrift={{
          drift_score: 0.4,
          position_dist_drift: 0,
          number_set_drift: 0,
          structure_drift: 0,
          score_gap_drift: 0,
          plan_overlap_drift: 0,
        }}
      />,
    );
    expect(screen.getByText(/mv-1/)).toBeInTheDocument();
    expect(screen.getByText(/72\.3/)).toBeInTheDocument();
    expect(screen.getByText("高")).toBeInTheDocument();
  });
});
