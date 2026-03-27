import type { Page } from "@playwright/test";

export async function installApiMock(page: Page) {
  const runs: Record<string, unknown>[] = [];

  await page.route("http://127.0.0.1:8091/api/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (method === "GET" && url.includes("/issues/status")) {
      return json({
        issueCount: 1,
        modelCount: 1,
        latestSyncAt: null,
        latestIssue: "25123",
        logCount: 1,
        schedulerLogs: [{ action: "sync", result: "ok", detail: "boot", timestamp: "2025-01-01T00:00:00Z" }],
        postmortems: [
          {
            issue: "25123",
            model_version: "mv",
            hit_summary: "pending draw result",
            weighted_return: 0,
            created_at: "2025-01-01T00:00:00Z",
          },
        ],
        optimizationRuns: [{ run_id: "opt_x", status: "queued", objective: "obj", created_at: "2025-01-01T00:00:00Z" }],
      });
    }

    if (method === "GET" && url.includes("/api/issues") && !url.includes("/status")) {
      return json({
        items: [{ issue: "25123", draw_date: "2025-01-01", front: [1, 2, 3, 4, 5], back: [1, 2] }],
      });
    }

    if (method === "GET" && url.includes("/models")) {
      return json({ items: [{ version: "mv", status: "champion", credit: 0.88 }] });
    }

    if (method === "GET" && url.includes("/runs")) {
      return json({ items: runs, limit: 50 });
    }

    if (method === "GET" && url.includes("/analysis/")) {
      return json({
        targetIssue: "next",
        modelVersion: "mv",
        snapshotHash: "deadbeef",
        seedHint: 42,
        positionProbabilities: {
          front: [
            {
              position: 1,
              top_numbers: [{ number: 1, raw_score: 0.1, calibrated_prob: 0.2, top_factors: [{ f: 0.1 }] }],
            },
          ],
          back: [
            {
              position: 1,
              top_numbers: [{ number: 1, raw_score: 0.1, calibrated_prob: 0.2, top_factors: [] }],
            },
          ],
        },
        featureSummary: {},
        structureBreakdown: {},
        notes: "e2e",
      });
    }

    if (method === "POST" && url.includes("/predict/")) {
      const run = {
        run_id: `run_${runs.length + 1}`,
        target_issue: "next",
        run_type: "experimental",
        model_version: "mv",
        seed: 20260326,
        created_at: "2025-01-01T00:00:01Z",
        plan1: [{ front: [1, 2, 3, 4, 5], back: [1, 2], score: 0.1, tags: [] }],
        plan2: [{ front: [5, 6, 7, 8, 9], back: [3, 4], score: 0.2, tags: [] }],
        drift: {
          drift_score: 0.18,
          position_delta: 0.1,
          set_delta: 0.1,
          structure_delta: 0.1,
          score_delta: 0.1,
          overlap_delta: 0.1,
        },
      };
      runs.push(run);
      return json({ ok: true, run });
    }

    if (method === "POST" && url.includes("/sync")) {
      return json({
        ok: true,
        degraded: false,
        mode: "cache",
        syncedAt: "2025-01-01T00:00:00Z",
        issueCount: 1,
        newIssueCount: 0,
        ruleVersionCount: 1,
        warnings: [],
      });
    }

    return json({ ok: true });
  });
}
