import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { HistoryPane } from "./HistoryPane";
import type { DrawIssue } from "../types";

describe("HistoryPane", () => {
  it("selects issue", async () => {
    const onSelect = vi.fn();
    const issues: DrawIssue[] = [{ issue: "25101", front: [1, 2, 3, 4, 5], back: [1, 2] }];
    render(<HistoryPane issues={issues} selectedIssue="next" onSelectIssue={onSelect} />);
    const row = screen.getByTestId("history-item-25101");
    await userEvent.click(within(row).getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith("25101");
  });
});
