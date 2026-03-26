import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExperimentRunPanel } from "./ExperimentRunPanel";
import type { PredictionRun, Ticket } from "../types";

const t: Ticket = { front: [1, 2, 3, 4, 5], back: [1, 2], score: 0, tags: [] };

describe("ExperimentRunPanel", () => {
  it("filters by target issue", () => {
    const runs: PredictionRun[] = [
      { run_id: "a", target_issue: "next", model_version: "m", seed: 1, created_at: "t", plan1: [t], plan2: [] },
      { run_id: "b", target_issue: "25100", model_version: "m", seed: 1, created_at: "t", plan1: [t], plan2: [] },
    ];
    render(<ExperimentRunPanel runs={runs} targetIssue="25100" />);
    expect(screen.getByTestId("run-row-b")).toBeInTheDocument();
    expect(screen.queryByTestId("run-row-a")).not.toBeInTheDocument();
  });
});
