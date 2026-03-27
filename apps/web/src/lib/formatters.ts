import type { DriftReport, PostmortemSummary, Ticket } from "../types";

export function formatBall(n: number): string {
  return String(n).padStart(2, "0");
}

export function formatTicketLine(t: Ticket): string {
  const f = t.front.map(formatBall).join(" ");
  const b = t.back.map(formatBall).join(" ");
  return `${f} + ${b}`;
}

/** 由 drift_score 推导 UI 等级（与 M7 7.2 低/中/高 展示一致） */
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

export function driftLevelFromBackend(level: string | undefined): "low" | "medium" | "high" | "unknown" {
  if (!level) {
    return "unknown";
  }
  const u = level.toUpperCase();
  if (u === "NORMAL") {
    return "low";
  }
  if (u === "WARN") {
    return "medium";
  }
  if (u === "CRITICAL") {
    return "high";
  }
  return "unknown";
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
      return "--";
  }
}

export function postmortemStatus(pm: PostmortemSummary | null | undefined): "pending" | "recorded" {
  if (!pm) {
    return "pending";
  }
  const h = (pm.hit_summary || "").toLowerCase();
  if (h.includes("pending") || h.includes("wait")) {
    return "pending";
  }
  return "recorded";
}

export function summarizeDrift(d: DriftReport | null | undefined): string {
  if (!d) {
    return "暂无漂移数据";
  }
  const score = Number(d.drift_score ?? 0);
  const position = Number(d.position_dist_drift ?? 0);
  const setD = Number(d.number_set_drift ?? 0);
  return `综合分 ${score.toFixed(3)} | 位置 ${position.toFixed(3)} | 号码集 ${setD.toFixed(3)}`;
}
