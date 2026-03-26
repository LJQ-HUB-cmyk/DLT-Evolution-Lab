from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DrawIssue(BaseModel):
    issue: str
    draw_date: str | None = None
    front: list[int] = Field(default_factory=list, min_length=0, max_length=5)
    back: list[int] = Field(default_factory=list, min_length=0, max_length=2)
    source: str = "lottery.gov.cn"
    synced_at: datetime | None = None


class Ticket(BaseModel):
    front: list[int] = Field(min_length=5, max_length=5)
    back: list[int] = Field(min_length=2, max_length=2)
    score: float = 0.0
    tags: list[str] = Field(default_factory=list)


DriftLevel = Literal["NORMAL", "WARN", "CRITICAL"]


class DriftReport(BaseModel):
    """M4 drift contract (M3 legacy float fields removed; use sub-metrics below)."""

    run_id: str
    target_issue: str
    model_version: str
    snapshot_hash: str = ""
    position_dist_drift: float = 0.0
    number_set_drift: float = 0.0
    structure_drift: float = 0.0
    score_gap_drift: float = 0.0
    plan_overlap_drift: float = 0.0
    drift_score: float = 0.0
    drift_level: DriftLevel = "NORMAL"
    trigger_actions: list[str] = Field(default_factory=list)
    created_at: datetime


class SearchMeta(BaseModel):
    beam_width: int = 0
    candidate_count_front: int = 0
    candidate_count_back: int = 0
    pruned_count: int = 0


class PredictionRun(BaseModel):
    run_id: str
    target_issue: str
    run_type: Literal["official", "experimental"]
    model_version: str
    seed: int
    snapshot_hash: str = ""
    engine_version: str = ""
    plan1: list[Ticket] = Field(default_factory=list)
    plan2: list[Ticket] = Field(default_factory=list)
    feature_summary: dict[str, Any] = Field(default_factory=dict)
    position_summary: dict[str, Any] = Field(default_factory=dict)
    search_meta: dict[str, Any] = Field(default_factory=dict)
    drift: DriftReport | None = None
    created_at: datetime
    postmortem_status: Literal["pending", "completed", "skipped"] | None = None
    prize_summary: dict[str, Any] | None = None


class OfficialPrediction(BaseModel):
    target_issue: str
    run_id: str
    model_version: str
    published_at: datetime
    snapshot_hash: str = ""
    seed: int = 0
    engine_version: str = ""
    plan1: list[Ticket] = Field(default_factory=list)
    plan2: list[Ticket] = Field(default_factory=list)
    feature_summary: dict[str, Any] = Field(default_factory=dict)
    position_summary: dict[str, Any] = Field(default_factory=dict)
    search_meta: dict[str, Any] = Field(default_factory=dict)
    postmortem_status: Literal["pending", "completed", "skipped"] | None = None
    prize_summary: dict[str, Any] | None = None


ModelRegistryStatus = Literal["champion", "candidate", "watch", "unstable", "deprecated"]


class ModelVersion(BaseModel):
    version: str
    status: ModelRegistryStatus = "candidate"
    credit_score: float = Field(default=70.0, ge=0.0, le=100.0)
    created_at: datetime
    updated_at: datetime
    notes: str = ""
    promotion_evidence: dict[str, Any] | None = None
    drift_profile_ref: str | None = None
    last_gate_result: dict[str, Any] | None = None
    drift_summary: dict[str, Any] | None = None
    config_overrides: dict[str, Any] = Field(default_factory=dict)
    consecutive_warn_count: int = 0
    credit: float | None = None


class BacktestReport(BaseModel):
    report_id: str
    model_version: str
    target_window: str
    weighted_return: float
    calibration_error: float
    stability_score: float
    created_at: datetime


class PostmortemReport(BaseModel):
    postmortem_id: str | None = None
    issue: str
    model_version: str
    hit_summary: str = ""
    weighted_return: float = 0.0
    feature_changes: list[str] = Field(default_factory=list)
    created_at: datetime
    run_refs: list[str] = Field(default_factory=list)
    postmortem_score: float | None = None
    triggered_optimize: bool | None = None


class AnchorTicketState(BaseModel):
    model_version: str
    target_issue: str
    ticket: Ticket
    locked: bool = True
    updated_at: datetime


OptimizationRunStatus = Literal["queued", "running", "completed", "failed"]
OptimizeTriggerSource = Literal["manual", "auto_drift", "auto_credit"]


class OptimizationRun(BaseModel):
    run_id: str
    trigger_source: OptimizeTriggerSource = "manual"
    base_model_version: str = ""
    search_space_hash: str = ""
    study_summary: dict[str, Any] = Field(default_factory=dict)
    best_params: dict[str, Any] = Field(default_factory=dict)
    best_score: float | None = None
    gate_result: dict[str, Any] = Field(default_factory=dict)
    status: OptimizationRunStatus = "queued"
    started_at: str | None = None
    finished_at: str | None = None
    queued_at: str | None = None
    failed_reason: str | None = None
    budget_trials: int = 80
    time_limit_minutes: int = 45
