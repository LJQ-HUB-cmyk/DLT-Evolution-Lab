import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RunLogPanel } from "./RunLogPanel";

describe("RunLogPanel", () => {
  it("renders retry on error", async () => {
    const onRetry = vi.fn();
    render(<RunLogPanel logs={[]} errorMessage="failed" onRetry={onRetry} />);
    await userEvent.click(screen.getByText("重试刷新"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("renders scheduler rows", () => {
    render(
      <RunLogPanel
        logs={[
          { action: "predict", result: "ok", detail: "run_id=x", timestamp: "2025-01-01T00:00:00Z", target_issue: "next" },
        ]}
      />,
    );
    expect(screen.getByText("predict")).toBeInTheDocument();
    expect(screen.getByText(/run_id=x/)).toBeInTheDocument();
  });
});
