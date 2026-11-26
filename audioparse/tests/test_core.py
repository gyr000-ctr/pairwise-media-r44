import math

import pytest

import pcmparse

def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    return False


def _norm(v):
    return math.sqrt(sum(c * c for c in v))

def _wav():
    fmt = struct.pack("<HHIIHH", 1, 1, 8000, 8000, 1, 8)
    body = b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", 2) + b"\x01\x02"
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body


def _p():
    return pcmparse.PcmParse()


def _wav_with_junk():
    fmt = struct.pack("<HHIIHH", 1, 1, 8000, 8000, 1, 8)
    body = (b"JUNK" + struct.pack("<I", 1) + b"\x00\x00"
            + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"data" + struct.pack("<I", 1) + b"\x01\x00")
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body


def _aiff():
    comm = struct.pack(">hIh", 1, 8000, 8)
    body = b"COMM" + struct.pack(">I", len(comm)) + comm + b"SSND" + struct.pack(">I", 0)
    return b"FORM" + struct.pack(">I", 4 + len(body)) + b"AIFF" + body

CASES = [
    ("parse", lambda: _p().parse(_wav())['rate'] == 8000),
    ("channels", lambda: _p().parse(_wav())['channels'] == 1),
    ("bits", lambda: _p().parse(_wav())['bits'] == 8),
    ("build", lambda: isinstance(_p().build({'rate': 8000, 'channels': 1, 'bits': 8}), bytes)),
    ("bad_magic", lambda: _raises(lambda: _p().parse(b'XXXX' + b'\x00' * 32))),
    ("truncated", lambda: _raises(lambda: _p().parse(_wav()[:12]))),
    ("bad_fmt", lambda: _raises(lambda: _p().build({'rate': 0, 'channels': 1, 'bits': 8}))),
    ("type", lambda: isinstance(_p().parse(_wav()), dict)),
    ("det", lambda: _p().parse(_wav()) == _p().parse(_wav())),
    ("aiff", lambda: isinstance(_p().parse(_aiff()), dict)),
    ("empty", lambda: _raises(lambda: _p().parse(b''))),
    ("no_mut", lambda: _p().parse(_wav()) is not None),
    ("unknown_chunk", lambda: isinstance(_p().parse(_wav_with_junk()), dict)),
    ("build_type", lambda: isinstance(_p().build({'rate': 44100, 'channels': 2, 'bits': 16}), bytes)),
    ("keys", lambda: set(_p().parse(_wav())) >= {'rate', 'channels', 'bits'}),
]


@pytest.mark.parametrize("name,check", CASES, ids=[c[0] for c in CASES])
def test_spec(name, check):
    assert check() is True
