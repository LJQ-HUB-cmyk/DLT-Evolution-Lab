import type { DriftReport, PostmortemSummary, Ticket } from "../types";

export function formatBall(n: number): string {
  return String(n).padStart(2, "0");
}

export function formatTicketLine(t: Ticket): string {
  const f = t.front.map(formatBall).join(" ");
  const b = t.back.map(formatBall).join(" ");
  return `${f} + ${b}`;
}

/** Derive UI drift level from aggregate drift score (M4/M6 display). */
export function driftLevelFromScore(score: number | undefined): "low" | "medium" | "high" | "unknown" {
  if (score == null || Number.isNaN(score)) {
    return "unknown";
  }
  if (score < 0.15) {
    return "low";
  }
  if (score < 0.3) {
    return "medium";
  }
  return "high";
}

export function driftLevelLabel(level: ReturnType<typeof driftLevelFromScore>): string {
  switch (level) {
    case "low":
      return "低";
    case "medium":
      return "中";
    case "high":
      return "高";
    default:
      return "—";
  }
}

export function postmortemStatus(pm: PostmortemSummary | null | undefined): "pending" | "recorded" {
  if (!pm) {
    return "pending";
  }
  const h = (pm.hit_summary || "").toLowerCase();
  if (h.includes("pending") || h.includes("待")) {
    return "pending";
  }
  return "recorded";
}

export function summarizeDrift(d: DriftReport | null | undefined): string {
  if (!d) {
    return "暂无漂移数据";
  }
  return `综合 ${d.drift_score.toFixed(3)} · 位置 ${d.position_delta.toFixed(3)} · 集合 ${d.set_delta.toFixed(3)}`;
}
