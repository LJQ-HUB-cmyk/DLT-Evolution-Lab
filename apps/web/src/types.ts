/** 与 `apps/api/app/models/schemas.py` 对齐的展示层类型（M7 契约真源在后端）。 */

export type DrawIssue = {
  issue: string;
  draw_date?: string;
  front: number[];
  back: number[];
};

export type Ticket = {
  front: number[];
  back: number[];
  score: number;
  tags: string[];
};

/** 后端 DriftLevel: NORMAL | WARN | CRITICAL；展示层用 drift_score 映射低/中/高 */
export type DriftReport = {
  run_id?: string;
  target_issue?: string;
  model_version?: string;
  snapshot_hash?: string;
  position_dist_drift?: number;
  number_set_drift?: number;
  structure_drift?: number;
  score_gap_drift?: number;
  plan_overlap_drift?: number;
  drift_score: number;
  drift_level?: "NORMAL" | "WARN" | "CRITICAL" | string;
  trigger_actions?: string[];
  created_at?: string;
};

export type TopNumber = {
  number: number;
  raw_score: number;
  raw_prob?: number;
  calibrated_prob: number;
  top_factors?: Array<Record<string, number>>;
};

export type PositionBlock = {
  position: number;
  top_numbers: TopNumber[];
};

export type AnalysisResponse = {
  targetIssue: string;
  modelVersion: string;
  snapshotHash: string;
  seedHint: number;
  positionProbabilities: { front: PositionBlock[]; back: PositionBlock[] };
  featureSummary: Record<string, unknown>;
  structureBreakdown: Record<string, unknown>;
  notes: string;
};

export type PredictionRun = {
  run_id: string;
  target_issue: string;
  run_type?: "official" | "experimental";
  model_version: string;
  seed: number;
  snapshot_hash?: string;
  engine_version?: string;
  created_at: string;
  plan1: Ticket[];
  plan2: Ticket[];
  plan3: Ticket[];
  feature_summary?: Record<string, unknown>;
  position_summary?: Record<string, unknown>;
  search_meta?: Record<string, unknown>;
  drift?: DriftReport | null;
  postmortem_status?: string;
  prize_summary?: Record<string, unknown>;
};

export type ModelRegistryItem = {
  version: string;
  status: "champion" | "candidate" | "watch" | "unstable" | "deprecated" | string;
  credit_score: number;
  credit?: number;
  created_at?: string;
  updated_at?: string;
  notes?: string;
  promotion_evidence?: Record<string, unknown> | null;
  drift_profile_ref?: string | null;
  last_gate_result?: Record<string, unknown> | null;
  drift_summary?: Record<string, unknown> | null;
  config_overrides?: Record<string, unknown>;
  consecutive_warn_count?: number;
};

export type ModelsResponse = {
  items: ModelRegistryItem[];
};

export type OptimizationRun = {
  run_id: string;
  trigger_source?: string;
  base_model_version?: string;
  status: string;
  best_score?: number | null;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  failed_reason?: string | null;
  gate_result?: Record<string, unknown>;
  study_summary?: Record<string, unknown>;
  budget_trials?: number;
  time_limit_minutes?: number;
  objective?: string;
  created_at?: string;
  failure_reason?: string;
  gate_passed?: boolean;
  candidate_version?: string;
};

export type PostmortemSummary = {
  issue: string;
  model_version: string;
  hit_summary: string;
  weighted_return: number;
  feature_changes?: string[];
  created_at: string;
  postmortem_score?: number;
  prize_score?: number;
  structure_score?: number;
  stability_score?: number;
};

export type SchedulerLogEntry = {
  action: string;
  result: string;
  detail?: string;
  timestamp: string;
  target_issue?: string;
  snapshot_hash?: string;
  model_version?: string;
  duration_ms?: number;
};

export type IssueStatus = {
  issueCount: number;
  modelCount: number;
  latestSyncAt: string | null;
  latestIssue: string | null;
  logCount: number;
  schedulerLogs: SchedulerLogEntry[];
  postmortems: PostmortemSummary[];
  optimizationRuns: OptimizationRun[];
};

export type SyncSummary = {
  ok: boolean;
  degraded: boolean;
  mode: "live" | "cache" | "skipped" | string;
  syncedAt: string;
  issueCount: number;
  newIssueCount: number;
  ruleVersionCount: number;
  warnings: string[];
  historySync?: {
    ok?: boolean;
    degraded?: boolean;
    issueCount?: number;
    warnings?: string[];
  } | null;
  scheduler_context?: {
    trigger_source?: string;
    task_status?: string;
    task_id?: string;
    idempotency_key?: string;
  } | null;
};
