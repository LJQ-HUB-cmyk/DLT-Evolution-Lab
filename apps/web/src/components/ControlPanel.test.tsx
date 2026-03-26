import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ControlPanel } from "./ControlPanel";

describe("ControlPanel", () => {
  it("fires experiment and publish", async () => {
    const onExp = vi.fn();
    const onPub = vi.fn();
    render(
      <ControlPanel
        runs={[]}
        targetIssue="next"
        onTargetIssueChange={vi.fn()}
        onExperiment={onExp}
        onPublish={onPub}
        loading={false}
        publishing={false}
        apiError={null}
      />,
    );
    await userEvent.click(screen.getByTestId("btn-experiment"));
    await userEvent.click(screen.getByTestId("btn-publish"));
    expect(onExp).toHaveBeenCalled();
    expect(onPub).toHaveBeenCalled();
  });
});
