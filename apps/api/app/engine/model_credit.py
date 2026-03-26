from __future__ import annotations

from typing import Any, Literal

from app.models.schemas import DriftLevel

ALPHA = 0.8
BASE_REWARD = 70.0
DRIFT_PENALTY_SCALE = 40.0
INSTABILITY_PENALTY = 15.0

WARN_DECAY = 0.92
CRITICAL_DECAY = 0.85
STRUCT_DELTA_WARN = 0.05
STRUCT_DELTA_CRITICAL = 0.12
BEAM_SHRINK_CRITICAL = 0.20

CreditHealth = Literal["healthy", "watch", "unstable"]


def credit_health(credit_score: float) -> CreditHealth:
    if credit_score >= 70.0:
        return "healthy"
    if credit_score >= 50.0:
        return "watch"
    return "unstable"


def registry_status_from_credit(credit_score: float, prev_status: str) -> str:
    if credit_score < 50.0:
        return "unstable"
    if prev_status == "champion" and credit_score >= 50.0:
        return "champion"
    if credit_score < 70.0:
        return "watch"
    if prev_status == "unstable":
        return "watch"
    if prev_status in ("champion", "candidate", "deprecated"):
        return prev_status if prev_status != "deprecated" else "candidate"
    return prev_status


def update_credit_score(
    prev_credit: float,
    drift_score: float,
    *,
    reproducibility_alarm: bool = False,
) -> float:
    drift_penalty = DRIFT_PENALTY_SCALE * drift_score
    inst = INSTABILITY_PENALTY if reproducibility_alarm else 0.0
    target = BASE_REWARD - drift_penalty - inst
    nxt = ALPHA * prev_credit + (1.0 - ALPHA) * target
    return round(max(0.0, min(100.0, nxt)), 6)


def decay_factor_for_level(level: DriftLevel) -> float:
    if level == "CRITICAL":
        return CRITICAL_DECAY
    if level == "WARN":
        return WARN_DECAY
    return 1.0


def apply_drift_to_config(
    model_config: dict[str, Any],
    level: DriftLevel,
) -> dict[str, Any]:
    """Return a new config dict with structure_penalty tightened and beam shrunk on CRITICAL."""
    import copy

    cfg = copy.deepcopy(model_config)
    if level == "NORMAL":
        return cfg
    struct = cfg.setdefault("structure", {})
    for plan_key in ("plan1", "plan2"):
        sw = struct.setdefault(plan_key, {})
        delta = STRUCT_DELTA_CRITICAL if level == "CRITICAL" else STRUCT_DELTA_WARN
        for k in list(sw.keys()):
            sw[k] = float(sw[k]) + delta
    search = cfg.setdefault("search", {})
    beam = int(search.get("beam_width", 32))
    if level == "CRITICAL":
        search["beam_width"] = max(8, int(round(beam * (1.0 - BEAM_SHRINK_CRITICAL))))
    return cfg


def merge_config_overrides(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    import copy

    out = copy.deepcopy(base)
    if not overrides:
        return out
    for k, v in overrides.items():
        if k == "structure" and isinstance(v, dict):
            st = out.setdefault("structure", {})
            for pk, pv in v.items():
                if isinstance(pv, dict) and isinstance(st.get(pk), dict):
                    st[pk] = {**st.get(pk, {}), **pv}
                else:
                    st[pk] = pv
        elif k == "search" and isinstance(v, dict):
            out.setdefault("search", {}).update(v)
        elif k == "N_hist":
            out["N_hist"] = v
        else:
            out[k] = v
    return out


def should_enqueue_optimize(
    level: DriftLevel,
    credit_score: float,
    consecutive_warn: int,
) -> bool:
    if level == "CRITICAL":
        return True
    if consecutive_warn >= 3:
        return True
    if credit_score < 55.0:
        return True
    return False


def bump_consecutive_warn(level: DriftLevel, prev: int) -> int:
    if level == "NORMAL":
        return 0
    if level == "WARN":
        return prev + 1
    if level == "CRITICAL":
        return 0
    return prev
