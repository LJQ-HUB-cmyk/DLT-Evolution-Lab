from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class JsonStore:
    def __init__(self) -> None:
        from app.core.paths import storage_dir as _storage_dir

        self._storage = _storage_dir()
        self._storage.mkdir(parents=True, exist_ok=True)

    def read(self, filename: str, default: Any) -> Any:
        file_path = self._storage / filename
        if not file_path.exists():
            self.write(filename, default)
            return default
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def write(self, filename: str, payload: Any) -> None:
        file_path = self._storage / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def append_log(
        self,
        filename: str,
        action: str,
        result: str,
        detail: str = "",
        *,
        target_issue: str | None = None,
        snapshot_hash: str | None = None,
        model_version: str | None = None,
        duration_ms: int | None = None,
        **extra: Any,
    ) -> None:
        logs = self.read(filename, default={"logs": [], "idempotency": {}, "alert_state": {}})
        logs.setdefault("logs", [])
        logs.setdefault("idempotency", {})
        entry: dict[str, Any] = {
            "action": action,
            "result": result,
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if target_issue is not None:
            entry["target_issue"] = target_issue
        if snapshot_hash is not None:
            entry["snapshot_hash"] = snapshot_hash
        if model_version is not None:
            entry["model_version"] = model_version
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms
        for k, v in extra.items():
            if v is not None:
                entry[k] = v
        logs["logs"].append(entry)
        self.write(filename, logs)

