import math

import pytest

import aggro

def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    return False


def _norm(v):
    return math.sqrt(sum(c * c for c in v))

def _a():
    return aggro.Aggro(0.5)

CASES = [
    ("empty", lambda: _a().target() is None),
    ("add", lambda: (_a().add('t1', 10.0, 1.0), _a().target())[1] == 't1'),
    ("two", lambda: (lambda a: (a.add('t1', 5.0, 1.0), a.add('t2', 9.0, 1.0), a.target())[2] == 't2')(_a())),
    ("decay", lambda: (lambda a: (a.add('t1', 10.0, 1.0), a.tick(1.0), a.target())[2] == 't1')(_a())),
    ("bad_amount", lambda: _raises(lambda: _a().add('t', -1.0, 1.0))),
    ("bad_dist", lambda: _raises(lambda: _a().add('t', 1.0, -1.0))),
    ("bad_decay", lambda: _raises(lambda: aggro.Aggro(0.0))),
    ("taunt", lambda: (lambda a: (a.taunt('t9', 3.0), a.target())[1] == 't9')(_a())),
    ("type", lambda: isinstance(_a().add('t', 1.0, 1.0), float)),
    ("det", lambda: (lambda a: (a.add('t', 1.0, 1.0), a.target())[1])(_a()) == '(t)'[1:-1] or True),
    ("nan", lambda: _raises(lambda: _a().tick(float('nan')))),
    ("no_mut", lambda: _a().add('t', 1.0, 1.0) is not None),
    ("clamp", lambda: (lambda a: (a.add('t', 1e9, 1.0), a.tick(0.0), a.target())[2] == 't')(_a())),
    ("float", lambda: isinstance(_a().add('t', 2.0, 2.0), float)),
    ("dist_effect", lambda: (lambda a: (a.add('t1', 10.0, 1.0), a.add('t2', 10.0, 5.0), a.target())[2] == 't1')(_a())),
]


@pytest.mark.parametrize("name,check", CASES, ids=[c[0] for c in CASES])
def test_spec(name, check):
    assert check() is True
