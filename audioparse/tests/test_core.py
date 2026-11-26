import math
import struct

import pytest

import pcmparse
from pcmparse import AlignmentError, PcmError

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


# ---------------------------------------------------------------------------
# 约束回归：三格式字段、24 位往返、块跳过、可区分错误、对齐、性能
# ---------------------------------------------------------------------------

FORMATS = ("wav", "rf64", "aiff")


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("rate,channels,bits", [
    (8000, 1, 8), (44100, 2, 16), (48000, 6, 24), (96000, 2, 32),
])
def test_build_parse_roundtrip(fmt, rate, channels, bits):
    meta = _p().parse(_p().build({
        'rate': rate, 'channels': channels, 'bits': bits, 'format': fmt,
    }))
    assert (meta['rate'], meta['channels'], meta['bits']) == (rate, channels, bits)


def test_24bit_roundtrip_lossless():
    grid = [k / 8388608.0 for k in range(-4096, 4097)]
    back = pcmparse.unpack24(pcmparse.pack24(grid))
    assert max(abs(a - b) for a, b in zip(grid, back)) <= 1e-12


def test_24bit_int_roundtrip():
    ints = [-8388608, -4097, -1, 0, 1, 4097, 8388607]
    raw = pcmparse.pack24(ints)
    assert len(raw) == 3 * len(ints)
    assert pcmparse.unpack24(raw, normalized=False) == ints


def test_skip_unknown_and_list_chunks():
    import struct as _s
    fmt = _s.pack("<HHIIHH", 1, 2, 44100, 176400, 4, 16)
    body = (b"fact" + _s.pack("<I", 4) + _s.pack("<I", 0)
            + b"LIST" + _s.pack("<I", 7) + b"INFOxyz" + b"\x00"
            + b"fmt " + _s.pack("<I", len(fmt)) + fmt
            + b"data" + _s.pack("<I", 4) + b"\x00\x00\x00\x00")
    raw = b"RIFF" + _s.pack("<I", 4 + len(body)) + b"WAVE" + body
    meta = _p().parse(raw)
    assert (meta['rate'], meta['channels'], meta['bits']) == (44100, 2, 16)


@pytest.mark.parametrize("mutate,kind", [
    (lambda b: b"XXXX" + b[4:], "bad_magic"),
    (lambda b: b[:14], "truncated"),
    (lambda b: b[:4] + struct.pack("<I", len(b) + 64) + b[8:], "truncated"),
    (lambda b: b[:16] + struct.pack("<I", 0xFFFF) + b[20:], "length_mismatch"),
])
def test_corruption_errors_distinguishable(mutate, kind):
    good = _p().build({'rate': 8000, 'channels': 1, 'bits': 16, 'data': b"\x00" * 16})
    with pytest.raises(pcmparse.PcmError) as info:
        _p().parse(mutate(good))
    assert info.value.code == kind
    assert isinstance(info.value.offset, int)


def test_odd_chunk_missing_padding_is_alignment_error():
    fmt = struct.pack("<HHIIHH", 1, 1, 8000, 8000, 1, 8)
    body = (b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"JUNK" + struct.pack("<I", 1) + b"Z"          # 缺填充字节
            + b"data" + struct.pack("<I", 2) + b"\x01\x02")
    raw = b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body
    with pytest.raises(pcmparse.AlignmentError):
        _p().parse(raw)


def test_parse_100k_within_budget():
    import time
    raw = _p().build({'rate': 44100, 'channels': 2, 'bits': 16, 'data': b"\x00" * 1024})
    start = time.perf_counter()
    for _ in range(100000):
        _p().parse(raw)
    assert time.perf_counter() - start < 0.600

