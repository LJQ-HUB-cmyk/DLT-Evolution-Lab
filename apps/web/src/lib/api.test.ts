import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  API_BASE,
  fetchAnalysis,
  fetchIssueStatus,
  fetchIssues,
  fetchModels,
  fetchRuns,
  runPredict,
  runPublish,
  syncOfficialData,
} from "./api";
import { ApiError } from "./errors";

describe("api", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("fetchIssueStatus normalizes missing dashboard fields", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          issueCount: 2,
          modelCount: 1,
          latestSyncAt: null,
          latestIssue: "25100",
          logCount: 3,
        }),
        { status: 200 },
      ),
    );
    const s = await fetchIssueStatus();
    expect(s.schedulerLogs).toEqual([]);
    expect(s.postmortems).toEqual([]);
    expect(s.optimizationRuns).toEqual([]);
    expect(s.issueCount).toBe(2);
  });

  it("fetchIssueStatus returns empty when GET fails twice", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("network"));
    const s = await fetchIssueStatus();
    expect(s.issueCount).toBe(0);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("fetchIssues maps items", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ items: [{ issue: "1", front: [], back: [] }] }), { status: 200 }),
    );
    const items = await fetchIssues();
    expect(items).toHaveLength(1);
  });

  it("fetchRuns passes limit query", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    await fetchRuns(10);
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("limit=10");
  });

  it("fetchModels and fetchAnalysis return json", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            targetIssue: "next",
            modelVersion: "m",
            snapshotHash: "s",
            seedHint: 1,
            positionProbabilities: { front: [], back: [] },
            featureSummary: {},
            structureBreakdown: {},
            notes: "",
          }),
          { status: 200 },
        ),
      );
    expect(await fetchModels()).toEqual({ items: [] });
    expect(await fetchAnalysis("next")).not.toBeNull();
  });

  it("fetchIssues returns empty on non-ok", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("", { status: 503 }));
    const items = await fetchIssues();
    expect(items).toEqual([]);
  });

  it("API_BASE is configurable but has localhost fallback", () => {
    expect(API_BASE).toMatch(/^https?:\/\/.+\/api$/);
  });

  it("syncOfficialData parses body", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          degraded: false,
          mode: "live",
          syncedAt: "t",
          issueCount: 1,
          newIssueCount: 0,
          ruleVersionCount: 0,
          warnings: [],
        }),
        { status: 200 },
      ),
    );
    const s = await syncOfficialData();
    expect(s.ok).toBe(true);
  });

  it("syncOfficialData throws ApiError on non-ok", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: { error_code: "SYNC_FAILED", message: "bad gateway" } }), {
        status: 502,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(syncOfficialData()).rejects.toBeInstanceOf(ApiError);
  });

  it("syncOfficialData throws fallback ApiError when response body is not json", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("bad gateway", { status: 502 }));
    await expect(syncOfficialData()).rejects.toBeInstanceOf(ApiError);
  });

  it("runPredict throws ApiError on failure", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: { error_code: "INSUFFICIENT_HISTORY", message: "need data" } }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      }),
    );
    let caught: unknown;
    try {
      await runPredict("next");
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).code).toBe("INSUFFICIENT_HISTORY");
  });

  it("runPredict succeeds on ok", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await expect(runPredict("next", 1)).resolves.toBeUndefined();
  });

  it("runPublish throws on failure", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "gone" }), { status: 404 }));
    await expect(runPublish("25100")).rejects.toBeInstanceOf(ApiError);
  });

  it("runPublish throws on non-json failure body", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("internal error", { status: 500 }));
    await expect(runPublish("25100")).rejects.toBeInstanceOf(ApiError);
  });

  it("runPublish succeeds on ok", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await expect(runPublish("25100")).resolves.toBeUndefined();
  });
});
