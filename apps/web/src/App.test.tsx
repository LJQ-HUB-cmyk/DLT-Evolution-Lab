import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import * as api from "./lib/api";
import type { IssueStatus } from "./types";

function statusPayload(over: Partial<IssueStatus> = {}): IssueStatus {
  return {
    issueCount: 0,
    modelCount: 1,
    latestSyncAt: null,
    latestIssue: null,
    logCount: 0,
    schedulerLogs: [],
    postmortems: [],
    optimizationRuns: [],
    ...over,
  };
}

describe("App integration", () => {
  beforeEach(() => {
    vi.spyOn(api, "fetchIssues").mockResolvedValue([]);
    vi.spyOn(api, "fetchRuns").mockResolvedValue([]);
    vi.spyOn(api, "fetchIssueStatus").mockResolvedValue(statusPayload());
    vi.spyOn(api, "fetchAnalysis").mockResolvedValue({
      targetIssue: "next",
      modelVersion: "mv",
      snapshotHash: "sh",
      seedHint: 9,
      positionProbabilities: { front: [], back: [] },
      featureSummary: {},
      structureBreakdown: {},
      notes: "",
    });
    vi.spyOn(api, "fetchModels").mockResolvedValue({
      items: [{ version: "mv", status: "champion", credit_score: 72 }],
    });
    vi.spyOn(api, "syncOfficialData").mockResolvedValue({
      ok: true,
      degraded: false,
      mode: "live",
      syncedAt: "t",
      issueCount: 0,
      newIssueCount: 0,
      ruleVersionCount: 0,
      warnings: [],
    });
    vi.spyOn(api, "runPredict").mockResolvedValue();
    vi.spyOn(api, "runPublish").mockResolvedValue({
      ok: true,
      officialPrediction: { target_issue: "next", run_id: "r1", published_at: "t", model_version: "mv" },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it(
    "loads and triggers experiment with partial refresh",
    async () => {
      render(<App />);
      await waitFor(() => expect(screen.getByTestId("app-root")).toBeInTheDocument());
      const btn = await screen.findByTestId("btn-experiment", {}, { timeout: 15_000 });
      await userEvent.click(btn);
      await waitFor(() => expect(api.runPredict).toHaveBeenCalled(), { timeout: 15_000 });
      expect(api.fetchRuns).toHaveBeenCalled();
      const pub = await screen.findByTestId("btn-publish", {}, { timeout: 15_000 });
      await userEvent.click(pub);
      await waitFor(() => expect(api.runPublish).toHaveBeenCalled(), { timeout: 15_000 });
    },
    35_000,
  );

  it("shows backend empty hint when status and issues are empty", async () => {
    vi.mocked(api.fetchIssueStatus).mockResolvedValue(
      statusPayload({
        issueCount: 0,
        modelCount: 0,
        logCount: 0,
      }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByText(/无法连接后端/)).toBeInTheDocument(), { timeout: 25_000 });
  });

  it("shows degraded banner after sync returns warnings", async () => {
    vi.mocked(api.syncOfficialData).mockResolvedValue({
      ok: true,
      degraded: true,
      mode: "cache",
      syncedAt: "t",
      issueCount: 0,
      newIssueCount: 0,
      ruleVersionCount: 0,
      warnings: ["demo-warning"],
    });
    render(<App />);
    await screen.findByTestId("app-root");
    await userEvent.click(screen.getByRole("button", { name: /同步官方数据/ }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/同步降级/));
  });

  it(
    "toggles history drawer",
    async () => {
      render(<App />);
      await screen.findByTestId("app-root", {}, { timeout: 20_000 });
      await userEvent.click(screen.getByRole("button", { name: "历史开奖" }));
      expect(document.querySelector(".layout-grid.drawer-open")).not.toBeNull();
    },
    25_000,
  );

  it("shows api error when predict fails", async () => {
    vi.mocked(api.runPredict).mockRejectedValueOnce(new Error("predict-boom"));
    render(<App />);
    await userEvent.click(await screen.findByTestId("btn-experiment", {}, { timeout: 15_000 }));
    await waitFor(() => expect(screen.getByText(/局部刷新失败/)).toBeInTheDocument());
  });

  it("shows api error when publish fails", async () => {
    vi.mocked(api.runPublish).mockRejectedValueOnce(new Error("publish-boom"));
    render(<App />);
    await userEvent.click(await screen.findByTestId("btn-publish", {}, { timeout: 15_000 }));
    await waitFor(() => expect(screen.getByText(/局部刷新失败/)).toBeInTheDocument());
  });

  it("shows api error when sync fails", async () => {
    vi.mocked(api.syncOfficialData).mockRejectedValueOnce(new Error("sync-boom"));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /同步官方数据/ }));
    await waitFor(() => expect(screen.getByRole("alertdialog")).toBeInTheDocument());
    expect(screen.getAllByText(/同步失败，请检查后端状态/).length).toBeGreaterThanOrEqual(1);
  });

  it("shows status error when partial refresh fails", async () => {
    let n = 0;
    vi.mocked(api.fetchRuns).mockImplementation(async () => {
      n += 1;
      if (n === 1) {
        return [];
      }
      throw new Error("partial-fail");
    });
    render(<App />);
    await screen.findByTestId("btn-experiment");
    await userEvent.click(screen.getByTestId("btn-experiment"));
    await waitFor(() => expect(screen.getByText(/局部刷新失败/)).toBeInTheDocument());
  });

  it("retries refresh from run log panel", async () => {
    vi.mocked(api.fetchIssueStatus).mockResolvedValue(
      statusPayload({
        issueCount: 0,
        modelCount: 0,
        logCount: 0,
      }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByText(/无法连接后端/)).toBeInTheDocument(), { timeout: 25_000 });
    vi.mocked(api.fetchIssueStatus).mockResolvedValue(
      statusPayload({
        issueCount: 1,
        modelCount: 1,
        logCount: 1,
        schedulerLogs: [{ action: "sync", result: "ok", timestamp: "t" }],
      }),
    );
    await userEvent.click(screen.getByText("重试刷新"));
    await waitFor(() => expect(screen.queryByText(/无法连接后端/)).not.toBeInTheDocument());
  });
});
