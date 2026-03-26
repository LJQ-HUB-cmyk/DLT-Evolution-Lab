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

export type DriftReport = {
  drift_score: number;
  position_delta: number;
  set_delta: number;
  structure_delta: number;
  score_delta: number;
  overlap_delta: number;
  unstable?: boolean;
  reason?: string;
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
  feature_summary?: Record<string, unknown>;
  position_summary?: Record<string, unknown>;
  search_meta?: Record<string, unknown>;
  drift?: DriftReport | null;
};

export type ModelRegistryItem = {
  version: string;
  status: "champion" | "candidate" | "unstable";
  credit: number;
  created_at?: string;
  updated_at?: string;
  notes?: string;
};

export type ModelsResponse = {
  items: ModelRegistryItem[];
};

export type OptimizationRun = {
  run_id: string;
  status: string;
  objective?: string;
  created_at: string;
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
