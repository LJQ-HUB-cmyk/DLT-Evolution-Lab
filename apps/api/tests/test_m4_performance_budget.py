from __future__ import annotations

import time

from datetime import datetime, timezone

from app.engine.drift import compute_drift_report


def test_drift_compute_under_budget_ms():
    baseline = {
        "position_summary": {"calibrated": {"front": [], "back": []}},
        "plan1": [{"front": [1, 2, 3, 4, 5], "back": [1, 2], "score": 1.0} for _ in range(5)],
        "plan2": [{"front": [6, 7, 8, 9, 10], "back": [3, 4], "score": 1.0} for _ in range(5)],
    }
    baseline["position_summary"] = {
        "calibrated": {
            "front": [
                {"top_numbers": [{"number": i, "calibrated_prob": 0.02} for i in range(1, 13)]}
                for _ in range(5)
            ],
            "back": [
                {"top_numbers": [{"number": i, "calibrated_prob": 1 / 6} for i in range(1, 7)]} for _ in range(2)
            ],
        }
    }
    current = baseline.copy()
    times = []
    for _ in range(15):
        t0 = time.perf_counter()
        compute_drift_report(
            run_id="perf",
            target_issue="x",
            model_version="mv",
            snapshot_hash="s",
            baseline=baseline,
            current=current,
            history_runs=[],
            created_at=datetime.now(timezone.utc),
        )
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    p95 = times[int(0.95 * (len(times) - 1))]
    assert p95 < 350.0
