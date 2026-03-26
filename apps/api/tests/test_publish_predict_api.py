from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.json_store import JsonStore


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch, patch_issues):
    st = tmp_path / "storage"
    st.mkdir(parents=True)
    monkeypatch.setattr("app.core.paths.storage_dir", lambda: st)
    import app.routers.api as api_mod

    api_mod.store = JsonStore()
    (st / "model_registry.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "version": "m3-test",
                        "status": "champion",
                        "credit": 1.0,
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "notes": "",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (st / "predictions.json").write_text(
        json.dumps({"official": [], "experimental": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    return TestClient(app)


def test_publish_idempotent(api_client: TestClient):
    r1 = api_client.post("/api/publish/25199", params={"seed": 11})
    assert r1.status_code == 200
    j1 = r1.json()["officialPrediction"]
    r2 = api_client.post("/api/publish/25199", params={"seed": 99})
    assert r2.status_code == 200
    assert r2.json().get("idempotent") is True
    assert r2.json()["officialPrediction"]["run_id"] == j1["run_id"]


def test_predict_new_run_each_call(api_client: TestClient):
    ids = set()
    for _ in range(5):
        r = api_client.post("/api/predict/next", params={"seed": 42})
        assert r.status_code == 200
        ids.add(r.json()["run"]["run_id"])
    assert len(ids) == 5
