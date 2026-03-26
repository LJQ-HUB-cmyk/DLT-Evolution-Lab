from __future__ import annotations

import json
from pathlib import Path

from app.services import predict_pipeline as pp


def test_rule_version_id_prefers_latest_version_id(tmp_path: Path, monkeypatch):
    (tmp_path / "rule_versions.json").write_text(
        json.dumps(
            {
                "items": [
                    {"id": "rv-legacy"},
                    {"version_id": "rule_003"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pp, "normalized_data_dir", lambda: tmp_path)
    assert pp._rule_version_id() == "rule_003"

