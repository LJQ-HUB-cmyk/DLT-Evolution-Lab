from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from app.engine import ENGINE_VERSION


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_json_bytes(obj: Any) -> bytes:
    return canonical_json(obj).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_snapshot_hash(
    history_slice: list[dict[str, Any]],
    model_config: dict[str, Any],
    rule_version_id: str,
) -> str:
    payload = {
        "history": history_slice,
        "model_config": model_config,
        "rule_version_id": rule_version_id,
    }
    return sha256_hex(canonical_json_bytes(payload))


def hash64_to_seed_int(h64: int) -> int:
    mask = (1 << 63) - 1
    return int(h64 & mask)


def mix_seed_ints(snapshot_hash: str, model_version: str, seed: int | str) -> int:
    raw = f"{snapshot_hash}|{model_version}|{seed}"
    h = hashlib.sha256(raw.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False)


def build_rng(snapshot_hash: str, model_version: str, seed: int | str) -> np.random.Generator:
    seed_int = mix_seed_ints(snapshot_hash, model_version, seed)
    return np.random.Generator(np.random.PCG64(seed_int))


def stable_response_hash(payload: dict[str, Any]) -> str:
    """Strip ephemeral fields for reproducibility checks."""
    stripped = {k: v for k, v in payload.items() if k not in ("run_id", "created_at", "published_at")}
    return sha256_hex(canonical_json_bytes(stripped))


__all__ = [
    "ENGINE_VERSION",
    "build_rng",
    "build_snapshot_hash",
    "canonical_json",
    "canonical_json_bytes",
    "mix_seed_ints",
    "sha256_hex",
    "stable_response_hash",
]
