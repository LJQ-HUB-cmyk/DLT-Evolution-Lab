from __future__ import annotations

from typing import Any, Callable

from app.services.json_store import JsonStore
from app.services.model_registry_service import try_promote_candidate


def promote_candidate_if_gate_passes(
    store: JsonStore,
    candidate_version: str,
    gate_builder: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """M4: candidate promotion is only allowed when gate_builder returns passed=True."""
    return try_promote_candidate(store, candidate_version, gate_builder=gate_builder)
