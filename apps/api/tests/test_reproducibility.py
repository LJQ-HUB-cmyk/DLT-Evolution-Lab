from __future__ import annotations

import numpy as np

from app.engine.reproducibility import build_rng, build_snapshot_hash, mix_seed_ints, stable_response_hash


def test_snapshot_hash_changes_with_history():
    h1 = build_snapshot_hash([{"issue": "1", "front": [1, 2, 3, 4, 5], "back": [1, 2]}], {"a": 1}, "rv1")
    h2 = build_snapshot_hash([{"issue": "1", "front": [1, 2, 3, 4, 6], "back": [1, 2]}], {"a": 1}, "rv1")
    assert h1 != h2


def test_mix_seed_deterministic():
    assert mix_seed_ints("ab" * 16, "m1", 3) == mix_seed_ints("ab" * 16, "m1", 3)


def test_rng_deterministic_streams():
    r1 = build_rng("h" * 64, "mv", 99)
    r2 = build_rng("h" * 64, "mv", 99)
    assert np.allclose(r1.random(5), r2.random(5))


def test_stable_response_hash_ignores_ephemeral():
    a = {"run_id": "a", "x": 1, "created_at": "t1"}
    b = {"run_id": "b", "x": 1, "created_at": "t2"}
    assert stable_response_hash(a) == stable_response_hash(b)
