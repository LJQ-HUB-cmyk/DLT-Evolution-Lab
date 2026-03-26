from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.json_store import JsonStore
from app.services.optimization_service import should_trigger_optimize


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JsonStore:
    st = tmp_path / "storage"
    st.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    s = JsonStore()
    low_scores = [{"postmortem_score": 10.0, "hit_matrix": [], "prize_distribution": {}} for _ in range(6)]
    s.write("postmortems.json", {"items": low_scores})
    s.write("predictions.json", {"official": [], "experimental": []})
    return s


def test_trigger_on_low_rolling_mean(store: JsonStore) -> None:
    should, reasons = should_trigger_optimize(store, score_threshold=55.0)
    assert should is True
    assert "rolling_mean_postmortem_score_low" in reasons
