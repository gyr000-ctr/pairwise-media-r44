import math

import pytest

import buffstack

def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    return False


def _norm(v):
    return math.sqrt(sum(c * c for c in v))

def _b():
    return buffstack.BuffStack()

CASES = [
    ("empty", lambda: _b().active() == []),
    ("apply", lambda: (lambda b: (b.apply('atk', 1.0, 1, 'stack'), len(b.active()))[1] == 1)(_b())),
    ("refresh", lambda: (lambda b: (b.apply('atk', 1.0, 1, 'refresh'), b.tick(0.5), b.apply('atk', 1.0, 1, 'refresh'), b.remaining('atk'))[3] > 0.9)(_b())),
    ("stack", lambda: (lambda b: (b.apply('atk', 1.0, 3, 'stack'), b.apply('atk', 1.0, 3, 'stack'), b.stacks('atk'))[2] == 2)(_b())),
    ("cap", lambda: (lambda b: ([b.apply('atk', 1.0, 2, 'stack') for _ in range(5)], b.stacks('atk'))[1] == 2)(_b())),
    ("expire", lambda: (lambda b: (b.apply('atk', 0.1, 1, 'stack'), b.tick(1.0), b.active())[2] == [])(_b())),
    ("bad_stacks", lambda: _raises(lambda: _b().apply('atk', 1.0, 0, 'stack'))),
    ("bad_mode", lambda: _raises(lambda: _b().apply('atk', 1.0, 1, 'bogus'))),
    ("bad_dur", lambda: _raises(lambda: _b().apply('atk', 0.0, 1, 'stack'))),
    ("type", lambda: isinstance(_b().active(), list)),
    ("stacks_type", lambda: (lambda b: (b.apply('a', 1.0, 1, 'stack'), isinstance(b.stacks('a'), int))[1])(_b())),
    ("nan", lambda: _raises(lambda: _b().tick(float('nan')))),
    ("no_mut", lambda: _b().tick(0.1) is not None),
    ("commute", lambda: (lambda b: (b.apply('a', 1.0, 2, 'stack'), b.apply('b', 1.0, 1, 'stack'), len(b.active()))[2] == 2)(_b())),
    ("remaining_type", lambda: (lambda b: (b.apply('a', 1.0, 1, 'stack'), isinstance(b.remaining('a'), float))[1])(_b())),
]


@pytest.mark.parametrize("name,check", CASES, ids=[c[0] for c in CASES])
def test_spec(name, check):
    assert check() is True
