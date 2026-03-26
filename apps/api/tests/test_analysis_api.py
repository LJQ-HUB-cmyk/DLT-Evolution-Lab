from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.json_store import JsonStore


@pytest.fixture
def analysis_client(tmp_path: Path, monkeypatch, patch_issues):
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
    return TestClient(app)


def test_analysis_has_positions(analysis_client: TestClient):
    r = analysis_client.get("/api/analysis/next")
    assert r.status_code == 200
    data = r.json()
    assert data["modelVersion"] == "m3-test"
    assert "front" in data["positionProbabilities"]
    assert len(data["positionProbabilities"]["front"]) == 5
