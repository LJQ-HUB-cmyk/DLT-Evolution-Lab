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

const champion: ModelRegistryItem = { version: "mv-1", status: "champion", credit: 0.91 };

describe("ModelMetaPanel", () => {
  it("renders champion credit and drift pill", () => {
    render(
      <ModelMetaPanel
        analysis={analysis}
        loading={false}
        champion={champion}
        latestDrift={{ drift_score: 0.4, position_delta: 0, set_delta: 0, structure_delta: 0, score_delta: 0, overlap_delta: 0 }}
      />,
    );
    expect(screen.getByText(/mv-1/)).toBeInTheDocument();
    expect(screen.getByText(/0\.910/)).toBeInTheDocument();
    expect(screen.getByText("高")).toBeInTheDocument();
  });
});
