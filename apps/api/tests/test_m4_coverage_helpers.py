from __future__ import annotations

from app.engine.model_credit import merge_config_overrides


def test_merge_config_overrides_N_hist_and_nested_structure():
    base = {
        "N_hist": 100,
        "structure": {"plan1": {"odd_even": 1.0, "big_small": 1.0}, "plan2": {"odd_even": 0.5}},
        "search": {"beam_width": 32},
    }
    ov = {
        "N_hist": 120,
        "structure": {"plan1": {"odd_even": 2.0}},
        "search": {"beam_width": 40},
        "extra_key": 1,
    }
    m = merge_config_overrides(base, ov)
    assert m["N_hist"] == 120
    assert m["structure"]["plan1"]["odd_even"] == 2.0
    assert m["structure"]["plan1"]["big_small"] == 1.0
    assert m["search"]["beam_width"] == 40
    assert m["extra_key"] == 1


def test_merge_empty_overrides():
    base = {"N_hist": 50, "structure": {}, "search": {}}
    assert merge_config_overrides(base, {}) == base
