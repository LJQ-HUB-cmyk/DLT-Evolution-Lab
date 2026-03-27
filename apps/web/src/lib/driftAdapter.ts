/**
 * 将历史/混合格式的 drift 载荷规范化为 DriftReport（M7 唯一适配层，可在此标注删除窗口）。
 */
import type { DriftReport } from "../types";

type LegacyDrift = {
  position_delta?: number;
  set_delta?: number;
  structure_delta?: number;
  score_delta?: number;
  overlap_delta?: number;
  drift_score?: number;
};

export function normalizeDriftReport(raw: unknown): DriftReport | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const d = raw as Record<string, unknown>;
  const score = Number(d.drift_score ?? 0);
  const hasNew =
    d.position_dist_drift != null ||
    d.number_set_drift != null ||
    d.structure_drift != null ||
    d.run_id != null;
  if (hasNew) {
    return {
      run_id: d.run_id != null ? String(d.run_id) : undefined,
      target_issue: d.target_issue != null ? String(d.target_issue) : undefined,
      model_version: d.model_version != null ? String(d.model_version) : undefined,
      snapshot_hash: d.snapshot_hash != null ? String(d.snapshot_hash) : undefined,
      position_dist_drift: Number(d.position_dist_drift ?? 0),
      number_set_drift: Number(d.number_set_drift ?? 0),
      structure_drift: Number(d.structure_drift ?? 0),
      score_gap_drift: Number(d.score_gap_drift ?? 0),
      plan_overlap_drift: Number(d.plan_overlap_drift ?? 0),
      drift_score: score,
      drift_level: d.drift_level != null ? String(d.drift_level) : undefined,
      trigger_actions: Array.isArray(d.trigger_actions) ? (d.trigger_actions as string[]) : undefined,
      created_at: d.created_at != null ? String(d.created_at) : undefined,
    };
  }
  const leg = d as LegacyDrift;
  return {
    position_dist_drift: Number(leg.position_delta ?? 0),
    number_set_drift: Number(leg.set_delta ?? 0),
    structure_drift: Number(leg.structure_delta ?? 0),
    score_gap_drift: Number(leg.score_delta ?? 0),
    plan_overlap_drift: Number(leg.overlap_delta ?? 0),
    drift_score: score,
  };
}

export function attachNormalizedDrift<T extends { drift?: unknown }>(row: T): T & { drift: DriftReport | null } {
  return { ...row, drift: normalizeDriftReport(row.drift) };
}
