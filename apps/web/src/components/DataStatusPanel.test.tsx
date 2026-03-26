import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DataStatusPanel } from "./DataStatusPanel";
import type { IssueStatus, SyncSummary } from "../types";

const status: IssueStatus = {
  issueCount: 2,
  modelCount: 1,
  latestSyncAt: "t",
  latestIssue: "25100",
  logCount: 0,
  schedulerLogs: [],
  postmortems: [],
  optimizationRuns: [],
};

describe("DataStatusPanel", () => {
  it("shows sync ok summary without warnings row", () => {
    const onSync = vi.fn();
    const sum: SyncSummary = {
      ok: true,
      degraded: false,
      mode: "live",
      syncedAt: "now",
      issueCount: 2,
      newIssueCount: 0,
      ruleVersionCount: 1,
      warnings: [],
    };
    render(<DataStatusPanel status={status} syncSummary={sum} syncing={false} onSync={onSync} />);
    expect(screen.getByText(/同步成功/)).toBeInTheDocument();
    expect(screen.queryByText(/告警：/)).not.toBeInTheDocument();
  });

  it("shows degraded summary", async () => {
    const onSync = vi.fn();
    const sum: SyncSummary = {
      ok: true,
      degraded: true,
      mode: "cache",
      syncedAt: "now",
      issueCount: 2,
      newIssueCount: 0,
      ruleVersionCount: 1,
      warnings: ["w1"],
    };
    render(<DataStatusPanel status={status} syncSummary={sum} syncing={false} onSync={onSync} />);
    expect(screen.getByText(/同步降级/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /同步官方数据/ }));
    expect(onSync).toHaveBeenCalled();
  });
});
