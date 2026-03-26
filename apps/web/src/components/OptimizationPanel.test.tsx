import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OptimizationPanel } from "./OptimizationPanel";
import type { OptimizationRun } from "../types";

describe("OptimizationPanel", () => {
  it("renders run rows", () => {
    const runs: OptimizationRun[] = [
      { run_id: "opt_1", status: "queued", objective: "obj", created_at: "t", failure_reason: "boom" },
    ];
    render(<OptimizationPanel runs={runs} />);
    expect(screen.getByText("opt_1")).toBeInTheDocument();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });
});
