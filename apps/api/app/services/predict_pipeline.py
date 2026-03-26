from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.core.paths import normalized_data_dir, storage_dir
from app.engine import ENGINE_VERSION
from app.engine.calibration import apply_calibration, fit_calibrators, persist_calibration
from app.engine.features import build_features_for_draws, load_issues_dataframe
from app.engine.position_model import score_positions, train_bundle
from app.engine.reproducibility import build_rng, build_snapshot_hash, mix_seed_ints
from app.engine.search import soft_structure_score
from app.engine.ticketing import build_plan1, build_plan2
from app.models.schemas import OfficialPrediction, PredictionRun


MIN_HISTORY_ISSUES = 100


class PipelineError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _load_normalized_issues() -> list[dict[str, Any]]:
    path = normalized_data_dir() / "issues.json"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("items", []))


def _rule_version_id() -> str:
    path = normalized_data_dir() / "rule_versions.json"
    if not path.exists():
        return "rv-default"
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items", [])
    if not items:
        return "rv-default"
    latest = items[-1]
    return str(latest.get("version_id") or latest.get("id") or "rv-default")


def default_model_config() -> dict[str, Any]:
    return {
        "N_hist": 300,
        "search": {"beam_width": 32, "k_front": 12, "k_back": 6},
        "structure": {
            "plan1": {
                "odd_even": 1.0,
                "big_small": 1.0,
                "zone_balance": 1.2,
                "sum_band": 0.9,
                "span_band": 0.9,
                "hot_cold_mix": 0.8,
            },
            "plan2": {
                "odd_even": 0.6,
                "big_small": 0.6,
                "zone_balance": 0.9,
                "sum_band": 0.5,
                "span_band": 0.5,
                "hot_cold_mix": 0.5,
            },
        },
    }


def _champion_version(registry: dict[str, Any]) -> str:
    items = registry.get("items", [])
    for it in items:
        if it.get("status") == "champion":
            return str(it["version"])
    if items:
        return str(items[0]["version"])
    raise PipelineError("MODEL_NOT_FOUND", "No model in registry")


def _read_anchor(path: Path) -> tuple[list[int] | None, list[int] | None]:
    if not path.exists():
        return None, None
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    t = data.get("ticket")
    if not t:
        return None, None
    return list(t.get("front", [])), list(t.get("back", []))


def run_prediction(
    *,
    target_issue: str,
    mode: Literal["official", "experimental"],
    seed: int,
    model_version: str,
    model_config: dict[str, Any],
) -> dict[str, Any]:
    t0 = time.perf_counter()
    anchor_path = storage_dir() / "anchor_ticket.json"
    raw_issues = _load_normalized_issues()
    if len(raw_issues) < MIN_HISTORY_ISSUES:
        raise PipelineError(
            "INSUFFICIENT_HISTORY",
            f"Need at least {MIN_HISTORY_ISSUES} issues, got {len(raw_issues)}",
        )

    n_hist = int(model_config.get("N_hist", 300))
    history = load_issues_dataframe(raw_issues, target_issue if target_issue != "next" else None, n_hist)
    if len(history) < MIN_HISTORY_ISSUES:
        raise PipelineError(
            "INSUFFICIENT_HISTORY",
            f"Window has {len(history)} issues, need {MIN_HISTORY_ISSUES}",
        )

    rule_vid = _rule_version_id()
    hist_payload = [
        {"issue": str(x["issue"]), "front": sorted(x["front"]), "back": sorted(x["back"])} for x in history
    ]
    snapshot_hash = build_snapshot_hash(hist_payload, model_config, rule_vid)

    split = max(int(len(history) * 0.8), MIN_HISTORY_ISSUES // 2)
    if split >= len(history) - 5:
        split = len(history) - 20
    train_draws = history[:split]
    val_draws = history[split:]
    if len(val_draws) < 5:
        raise PipelineError("INSUFFICIENT_HISTORY", "Validation slice too small")

    rng_train = build_rng(snapshot_hash, model_version, "train_fit")
    bundle = train_bundle(train_draws, model_version, rng_train, min_hist=30)
    cal = fit_calibrators(bundle, train_draws, val_draws, model_version, min_hist=30)
    calibration_hash = persist_calibration(cal, model_version, snapshot_hash)

    feats_by_zone, feature_summary, feature_stats_hash = build_features_for_draws(
        history, model_version, persist=True
    )
    feature_summary["calibration_hash"] = calibration_hash
    feature_summary["feature_stats_hash"] = feature_stats_hash

    kf = int(model_config.get("search", {}).get("k_front", 12))
    kb = int(model_config.get("search", {}).get("k_back", 6))
    raw_pos = score_positions(bundle, feats_by_zone, top_n_front=kf, top_n_back=kb)
    calibrated = apply_calibration(cal, bundle, raw_pos)

    anchor_f, anchor_b = _read_anchor(anchor_path)

    rng_exp = build_rng(snapshot_hash, model_version, seed)
    plan1, sm1 = build_plan1(calibrated, feats_by_zone, anchor_f, anchor_b, model_config)
    plan2, sm2 = build_plan2(calibrated, feats_by_zone, model_config, rng_exp)

    search_meta = {"plan1": sm1, "plan2": sm2}

    duration_ms = int((time.perf_counter() - t0) * 1000)

    position_summary: dict[str, Any] = {
        "calibrated": calibrated,
        "raw_metrics": cal.metrics,
    }

    base = {
        "target_issue": target_issue,
        "model_version": model_version,
        "snapshot_hash": snapshot_hash,
        "seed": seed,
        "engine_version": ENGINE_VERSION,
        "plan1": [t.model_dump(mode="json") for t in plan1],
        "plan2": [t.model_dump(mode="json") for t in plan2],
        "feature_summary": feature_summary,
        "position_summary": position_summary,
        "search_meta": search_meta,
        "_duration_ms": duration_ms,
    }

    if mode == "official":
        run_id = f"official_{target_issue}_{model_version}_{seed}"
        pred = OfficialPrediction(
            target_issue=target_issue,
            run_id=run_id,
            model_version=model_version,
            published_at=datetime.now(timezone.utc),
            snapshot_hash=snapshot_hash,
            seed=seed,
            engine_version=ENGINE_VERSION,
            plan1=plan1,
            plan2=plan2,
            feature_summary=feature_summary,
            position_summary=position_summary,
            search_meta=search_meta,
        )
        return {**base, "officialPrediction": pred.model_dump(mode="json")}

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    run = PredictionRun(
        run_id=run_id,
        target_issue=target_issue,
        run_type="experimental",
        model_version=model_version,
        seed=seed,
        snapshot_hash=snapshot_hash,
        engine_version=ENGINE_VERSION,
        plan1=plan1,
        plan2=plan2,
        feature_summary=feature_summary,
        position_summary=position_summary,
        search_meta=search_meta,
        drift=None,
        created_at=datetime.now(timezone.utc),
    )
    return {**base, "run": run.model_dump(mode="json")}


def build_analysis_payload(target_issue: str, model_version: str, model_config: dict[str, Any]) -> dict[str, Any]:
    raw_issues = _load_normalized_issues()
    if len(raw_issues) < MIN_HISTORY_ISSUES:
        raise PipelineError(
            "INSUFFICIENT_HISTORY",
            f"Need at least {MIN_HISTORY_ISSUES} issues, got {len(raw_issues)}",
        )
    n_hist = int(model_config.get("N_hist", 300))
    history = load_issues_dataframe(raw_issues, target_issue if target_issue != "next" else None, n_hist)
    if len(history) < MIN_HISTORY_ISSUES:
        raise PipelineError("INSUFFICIENT_HISTORY", "Not enough history in window")

    rule_vid = _rule_version_id()
    hist_payload = [
        {"issue": str(x["issue"]), "front": sorted(x["front"]), "back": sorted(x["back"])} for x in history
    ]
    snapshot_hash = build_snapshot_hash(hist_payload, model_config, rule_vid)

    split = max(int(len(history) * 0.8), MIN_HISTORY_ISSUES // 2)
    if split >= len(history) - 5:
        split = len(history) - 20
    train_draws = history[:split]
    val_draws = history[split:]
    rng_train = build_rng(snapshot_hash, model_version, "train_fit")
    bundle = train_bundle(train_draws, model_version, rng_train, min_hist=30)
    cal = fit_calibrators(bundle, train_draws, val_draws, model_version, min_hist=30)

    feats_by_zone, feature_summary, _ = build_features_for_draws(history, model_version, persist=False)
    kf = int(model_config.get("search", {}).get("k_front", 12))
    kb = int(model_config.get("search", {}).get("k_back", 6))
    raw_pos = score_positions(bundle, feats_by_zone, top_n_front=kf, top_n_back=kb)
    calibrated = apply_calibration(cal, bundle, raw_pos)

    structure_weights = model_config.get("structure", {}).get("plan1", {})

    demo_front = list(range(1, 6))
    demo_back = [1, 2]
    structure_breakdown = {
        "weights": structure_weights,
        "demo_score": float(soft_structure_score(demo_front, demo_back, structure_weights, feats_by_zone)),
    }

    return {
        "targetIssue": target_issue,
        "modelVersion": model_version,
        "snapshotHash": snapshot_hash,
        "seedHint": int(mix_seed_ints(snapshot_hash, model_version, 0) % 1_000_000),
        "positionProbabilities": {
            "front": calibrated["front"],
            "back": calibrated["back"],
        },
        "featureSummary": feature_summary,
        "structureBreakdown": structure_breakdown,
        "notes": "M3 analysis",
    }
