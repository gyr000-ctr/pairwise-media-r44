import math

import pytest

import inventory

def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    return False


def _norm(v):
    return math.sqrt(sum(c * c for c in v))

def _i():
    return inventory.Inventory(4, 4, False)

CASES = [
    ("place", lambda: len(_i().place((2, 2))) == 2),
    ("used", lambda: (_i().place((2, 2)), _i().used())[1] == 4),
    ("no_overlap", lambda: (_i().place((2, 2)), _i().place((2, 2)), _i().used())[2] <= 8),
    ("full", lambda: (_i().place((2, 2)), _i().place((2, 2)), _i().place((2, 2)), _i().place((2, 2)), _i().place((1, 1)))[4] is None),
    ("rotate", lambda: isinstance(inventory.Inventory(2, 4, True).place((4, 2)), tuple)),
    ("bad_size", lambda: _raises(lambda: inventory.Inventory(0, 4))),
    ("bad_item", lambda: _raises(lambda: _i().place((0, 1)))),
    ("too_big", lambda: (_i().place((9, 9))) is None),
    ("type", lambda: isinstance(_i().place((1, 1)), tuple)),
    ("grid_type", lambda: isinstance(_i().grid(), list)),
    ("used_type", lambda: (_i().place((1, 1)), isinstance(_i().used(), int))[1]),
    ("no_mut", lambda: _i().place((1, 1)) is not None),
    ("nan", lambda: _raises(lambda: _i().place((float('nan'), 1)))),
    ("bounds", lambda: all(0 <= c <= 4 for c in _i().place((2, 2)))),
    ("repeat", lambda: (_i().place((4, 4)), _i().place((1, 1)))[1] is None),
]


@pytest.mark.parametrize("name,check", CASES, ids=[c[0] for c in CASES])
def test_spec(name, check):
    assert check() is True
