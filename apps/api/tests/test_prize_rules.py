from __future__ import annotations

import pytest

from app.services.postmortem_service import map_prize_level


@pytest.mark.parametrize(
    ("fh", "bh", "expected"),
    [
        (5, 2, 1),
        (5, 1, 2),
        (5, 0, 3),
        (4, 2, 4),
        (4, 1, 5),
        (3, 2, 6),
        (4, 0, 7),
        (3, 1, 8),
        (2, 2, 8),
        (3, 0, 9),
        (2, 1, 9),
        (1, 2, 9),
        (0, 2, 9),
        (2, 0, "no_prize"),
        (1, 1, "no_prize"),
        (0, 0, "no_prize"),
    ],
)
def test_map_prize_level(fh: int, bh: int, expected: int | str) -> None:
    assert map_prize_level(fh, bh) == expected
