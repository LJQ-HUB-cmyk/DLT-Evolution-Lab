from __future__ import annotations

from datetime import datetime, timezone

from app.models.schemas import OfficialPrediction, PredictionRun, Ticket


def test_official_prediction_optional_fields():
    o = OfficialPrediction(
        target_issue="25100",
        run_id="r1",
        model_version="mv",
        published_at=datetime.now(timezone.utc),
        snapshot_hash="ab" * 32,
        seed=1,
        engine_version="m3.0.0",
        plan1=[Ticket(front=[1, 2, 3, 4, 5], back=[1, 2])],
        plan2=[Ticket(front=[5, 6, 7, 8, 9], back=[3, 4])],
        feature_summary={"k": 1},
        position_summary={"p": 2},
        search_meta={"s": 3},
    )
    d = o.model_dump(mode="json")
    assert d["snapshot_hash"] and d["engine_version"]
    for k in ("target_issue", "run_id", "plan1", "plan2", "published_at"):
        assert k in d


def test_prediction_run_experimental_shape():
    r = PredictionRun(
        run_id="run_x",
        target_issue="next",
        run_type="experimental",
        model_version="mv",
        seed=2,
        snapshot_hash="cd" * 32,
        engine_version="m3.0.0",
        feature_summary={"a": 1},
        position_summary={"b": 2},
        search_meta={"c": 3},
        created_at=datetime.now(timezone.utc),
    )
    d = r.model_dump(mode="json")
    assert "feature_summary" in d and "position_summary" in d
