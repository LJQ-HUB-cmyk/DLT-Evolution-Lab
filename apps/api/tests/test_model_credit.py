from __future__ import annotations

from app.engine.model_credit import (
    bump_consecutive_warn,
    credit_health,
    decay_factor_for_level,
    registry_status_from_credit,
    should_enqueue_optimize,
    update_credit_score,
)


def test_credit_update_normal_drift():
    n = update_credit_score(70.0, 0.1, reproducibility_alarm=False)
    assert 0.0 <= n <= 100.0
    assert n < 70.0


def test_credit_update_repro_alarm_penalty():
    a = update_credit_score(70.0, 0.0, reproducibility_alarm=False)
    b = update_credit_score(70.0, 0.0, reproducibility_alarm=True)
    assert b < a


def test_decay_factors():
    assert abs(decay_factor_for_level("NORMAL") - 1.0) <= 1e-9
    assert abs(decay_factor_for_level("WARN") - 0.92) <= 1e-9
    assert abs(decay_factor_for_level("CRITICAL") - 0.85) <= 1e-9


def test_should_enqueue_critical():
    assert should_enqueue_optimize("CRITICAL", 80.0, 0) is True


def test_should_enqueue_three_warns():
    assert should_enqueue_optimize("WARN", 80.0, 3) is True


def test_should_enqueue_low_credit():
    assert should_enqueue_optimize("NORMAL", 50.0, 0) is True


def test_bump_consecutive_warn_resets():
    assert bump_consecutive_warn("NORMAL", 5) == 0
    assert bump_consecutive_warn("WARN", 2) == 3
    assert bump_consecutive_warn("CRITICAL", 2) == 0


def test_credit_health_buckets():
    assert credit_health(80) == "healthy"
    assert credit_health(60) == "watch"
    assert credit_health(40) == "unstable"


def test_registry_status_from_credit_champion():
    assert registry_status_from_credit(65, "champion") == "champion"
    assert registry_status_from_credit(40, "champion") == "unstable"


def test_should_enqueue_false_when_normal():
    assert should_enqueue_optimize("NORMAL", 70.0, 0) is False
