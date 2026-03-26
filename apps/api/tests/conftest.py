from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


def _synthetic_issue_list(n: int, seed: int = 42) -> list[dict]:
    rng = np.random.default_rng(seed)
    items = []
    base = 24000
    for i in range(n):
        issue = str(base + i)
        front = sorted(rng.choice(np.arange(1, 36), size=5, replace=False).tolist())
        back = sorted(rng.choice(np.arange(1, 13), size=2, replace=False).tolist())
        items.append({"issue": issue, "front": front, "back": back, "draw_date": None})
    return items


@pytest.fixture
def synthetic_issues() -> list[dict]:
    return _synthetic_issue_list(130, seed=7)


@pytest.fixture
def patch_issues(monkeypatch, synthetic_issues, tmp_path: Path):
    (tmp_path / "issues.json").write_text(
        json.dumps({"items": synthetic_issues}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "rule_versions.json").write_text(
        json.dumps({"items": [{"id": "rv-test"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    def _norm_dir():
        return tmp_path

    monkeypatch.setattr("app.services.predict_pipeline.normalized_data_dir", _norm_dir)

    import app.services.predict_pipeline as pp

    _orig_cfg = pp.default_model_config

    def _fast_model_config():
        c = _orig_cfg()
        c["N_hist"] = min(100, len(synthetic_issues))
        c["search"] = {"beam_width": 16, "k_front": 8, "k_back": 4}
        return c

    monkeypatch.setattr(pp, "default_model_config", _fast_model_config)
    import app.routers.api as api_mod

    monkeypatch.setattr(api_mod, "default_model_config", _fast_model_config)
    return synthetic_issues
