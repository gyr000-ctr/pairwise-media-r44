import math

import pytest

import damageover
from damageover import dot

def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    return False


def _norm(v):
    return math.sqrt(sum(c * c for c in v))

def _d():
    return dot.Dot(0.5)

CASES = [
    ("apply", lambda: (_d().apply('poison', 10.0, 2.0), _d().total('poison'))[1] == 0.0),
    ("tick", lambda: (lambda d: (d.apply('poison', 10.0, 2.0), d.update(0.5), d.total('poison'))[2] > 0.0)(_d())),
    ("total_rate", lambda: (lambda d: (d.apply('poison', 10.0, 2.0), d.update(2.0), d.total('poison'))[2] <= 20.0 + 1e-6)(_d())),
    ("expire", lambda: (lambda d: (d.apply('poison', 10.0, 0.5), d.update(1.0), d.active())[2] == [])(_d())),
    ("bad_tick", lambda: _raises(lambda: dot.Dot(0.0))),
    ("bad_dps", lambda: _raises(lambda: _d().apply('p', -1.0, 1.0))),
    ("bad_dur", lambda: _raises(lambda: _d().apply('p', 1.0, 0.0))),
    ("two", lambda: (lambda d: (d.apply('a', 5.0, 1.0), d.apply('b', 7.0, 1.0), len(d.active()))[2] == 2)(_d())),
    ("type", lambda: isinstance(_d().total('x') if _d().apply('x', 1.0, 1.0) else 0.0, float)),
    ("det", lambda: (lambda d: (d.apply('p', 1.0, 1.0), d.update(0.5), d.total('p'))[2])(_d()) == (lambda d: (d.apply('p', 1.0, 1.0), d.update(0.5), d.total('p'))[2])(_d())),
    ("nan", lambda: _raises(lambda: _d().update(float('nan')))),
    ("no_mut", lambda: _d().update(0.1) is not None),
    ("active_type", lambda: isinstance(_d().active(), list)),
    ("partial_tick", lambda: (lambda d: (d.apply('p', 4.0, 0.75), d.update(0.75), d.total('p'))[2] > 0.0)(_d())),
    ("total_type", lambda: (lambda d: (d.apply('p', 1.0, 1.0), isinstance(d.total('p'), float))[1])(_d())),
]


@pytest.mark.parametrize("name,check", CASES, ids=[c[0] for c in CASES])
def test_spec(name, check):
    assert check() is True
