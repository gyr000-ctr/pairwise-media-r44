"""pcmparse 核心 API：PCM 容器头解析（WAV / AIFF / RF64）。

仅使用 Python 标准库。公开接口：

- :class:`PcmParse` —— ``parse(data)`` / ``build(spec)``
- :func:`parse` / :func:`build` —— 模块级便捷函数
- :func:`pack24` / :func:`unpack24` —— 24 位打包/解包（归一化浮点）
- :func:`pack_pcm` / :func:`unpack_pcm` —— 任意位深的 PCM 打包/解包
- 一组可区分的 :class:`ValueError` 子类，均带 ``offset`` 属性：

  * :class:`TruncatedError`      —— 数据被截断
  * :class:`MagicError`          —— 容器/格式魔数错误
  * :class:`LengthMismatchError` —— 声明长度与可用数据不符
  * :class:`AlignmentError`      —— 偶字节对齐错误
  * :class:`FormatError`         —— 头部字段非法
  * :class:`MissingChunkError`   —— 缺少必需的块
"""

import struct

__all__ = [
    "PcmParse",
    "parse",
    "build",
    "pack24",
    "unpack24",
    "pack_pcm",
    "unpack_pcm",
    "encode_extended",
    "decode_extended",
    "PcmError",
    "TruncatedError",
    "MagicError",
    "BadMagicError",
    "LengthMismatchError",
    "AlignmentError",
    "MisalignmentError",
    "FormatError",
    "MissingChunkError",
]


# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------


class PcmError(ValueError):
    """所有解析/构造错误的基类（继承 ValueError）。"""

    kind = "pcm"

    def __init__(self, message, offset=None, **details):
        self.detail = message
        self.offset = offset
        self.details = details
        if offset is None:
            text = "%s: %s" % (self.kind, message)
        else:
            text = "%s: %s (offset %d)" % (self.kind, message, offset)
        super().__init__(text)

    @property
    def code(self):
        """错误类别的稳定字符串标识（与 ``kind`` 相同）。"""
        return self.kind


class TruncatedError(PcmError):
    """数据比容器头声明/块头要求的少。"""

    kind = "truncated"


class MagicError(PcmError):
    """魔数或容器类型不认识。"""

    kind = "bad_magic"


#: ``MagicError`` 的别名。
BadMagicError = MagicError


class LengthMismatchError(PcmError):
    """块声明长度与容器/文件可用长度不一致。"""

    kind = "length_mismatch"


class AlignmentError(PcmError):
    """块未按偶字节边界对齐（缺少填充字节）。"""

    kind = "alignment"


#: ``AlignmentError`` 的别名。
MisalignmentError = AlignmentError


class FormatError(PcmError):
    """头部字段非法或构造参数非法。"""

    kind = "format"


class MissingChunkError(PcmError):
    """缺少必需的块（例如 WAV 的 ``fmt `` / AIFF 的 ``COMM``）。"""

    kind = "missing_chunk"


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

_U16LE = struct.Struct("<H").unpack_from
_U32LE = struct.Struct("<I").unpack_from
_I16LE = struct.Struct("<h").unpack_from
_U16BE = struct.Struct(">H").unpack_from
_I16BE = struct.Struct(">h").unpack_from
_U32BE = struct.Struct(">I").unpack_from
_U64LE = struct.Struct("<Q").unpack_from

#: 常见块 id，用于检测奇数字节块后缺失的填充字节。
_KNOWN_CHUNK_IDS = frozenset(
    (
        b"fmt ",
        b"data",
        b"fact",
        b"LIST",
        b"JUNK",
        b"bext",
        b"cue ",
        b"smpl",
        b"inst",
        b"iXML",
        b"ds64",
        b"PEAK",
        b"COMM",
        b"SSND",
        b"ANNO",
        b"COMT",
        b"NAME",
        b"AUTH",
        b"(c) ",
        b"ID3 ",
        b"id3 ",
    )
)


def _u32le(data, pos):
    return _U32LE(data, pos)[0]


def _u32be(data, pos):
    return _U32BE(data, pos)[0]


def decode_extended(raw):
    """解码 80 位 IEEE 754 扩展精度（AIFF 采样率）。"""
    if len(raw) < 10:
        raise TruncatedError("extended float needs 10 bytes", offset=0)
    sign = -1.0 if raw[0] & 0x80 else 1.0
    exponent = ((raw[0] & 0x7F) << 8) | raw[1]
    mantissa = int.from_bytes(raw[2:10], "big")
    if exponent == 0 and mantissa == 0:
        return 0.0
    if exponent == 0x7FFF:
        if mantissa == 0:
            return sign * float("inf")
        return float("nan")
    # exponent bias 16383，尾数为无隐含位的 64 位整数。
    return sign * mantissa * 2.0 ** (exponent - 16383 - 63)


def encode_extended(value):
    """编码为 80 位 IEEE 754 扩展精度的 10 字节串（AIFF 采样率）。"""
    if value < 0:
        raise FormatError("sample rate must be non-negative", offset=None)
    if value == 0:
        return b"\x00" * 10
    if value != value or value in (float("inf"), float("-inf")):
        raise FormatError("sample rate must be finite", offset=None)
    if int(value) != value:
        # 非整数采样率：按浮点拆分；仍保留足够精度。
        mantissa, exponent = _frexp_int(value)
    else:
        n = int(value)
        exponent = n.bit_length() - 1
        mantissa = n << (63 - exponent)
    exponent += 16383
    if exponent > 0x7FFE:
        raise FormatError("sample rate too large", offset=None)
    first = exponent >> 8
    second = exponent & 0xFF
    return bytes((first, second)) + mantissa.to_bytes(8, "big")


def _frexp_int(value):
    """把正浮点数拆成 64 位整数尾数与二进制指数（无隐含位）。"""
    exp = 0
    v = float(value)
    while v >= 1.0:
        v /= 2.0
        exp += 1
    while v < 0.5:
        v *= 2.0
        exp -= 1
    mantissa = int(round(v * (1 << 64)))
    if mantissa >= (1 << 64):
        mantissa >>= 1
        exp += 1
    # v 位于 [0.5, 1)，尾数需要 63 位小数：与整数路径保持同样的指数口径。
    return mantissa, exp - 1


# ---------------------------------------------------------------------------
# 24 位 / 任意位深 PCM 打包
# ---------------------------------------------------------------------------

_SCALE24 = 8388608.0  # 2 ** 23


def _as_int_sample(sample, bits):
    lo = -(1 << (bits - 1))
    hi = (1 << (bits - 1)) - 1
    if isinstance(sample, int) and not isinstance(sample, bool):
        value = sample
    else:
        scale = float(1 << (bits - 1))
        value = int(round(float(sample) * scale))
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def pack24(samples):
    """把样本序列打包为 24 位小端有符号 PCM 字节串。

    ``samples`` 可以是 [-1.0, 1.0) 的浮点数，也可以是原始整数。
    落在 24 位格点上的浮点值（``k / 2**23``）可无损往返。
    """
    out = bytearray(3 * len(samples))
    i = 0
    for sample in samples:
        value = _as_int_sample(sample, 24) & 0xFFFFFF
        out[i] = value & 0xFF
        out[i + 1] = (value >> 8) & 0xFF
        out[i + 2] = (value >> 16) & 0xFF
        i += 3
    return bytes(out)


def unpack24(data, normalized=True):
    """把 24 位小端有符号 PCM 解包为样本列表。

    ``normalized=True``（默认）返回 ``/ 2**23`` 的浮点；否则返回整数。
    """
    n = len(data)
    if n % 3:
        raise LengthMismatchError(
            "24-bit payload length %d is not a multiple of 3" % n,
            offset=0,
            length=n,
        )
    result = []
    append = result.append
    if normalized:
        for i in range(0, n, 3):
            value = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16)
            if value & 0x800000:
                value -= 0x1000000
            append(value / _SCALE24)
    else:
        for i in range(0, n, 3):
            value = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16)
            if value & 0x800000:
                value -= 0x1000000
            append(value)
    return result


def pack_pcm(samples, bits=24, byte_order="little"):
    """按位深打包样本（8/16/24/32 位，有符号，除 8 位外补码）。"""
    if bits not in (8, 16, 24, 32):
        raise FormatError("unsupported bit depth %r" % (bits,), offset=None)
    if bits == 24:
        raw = pack24(samples)
        if byte_order == "little":
            return raw
        if byte_order == "big":
            flipped = bytearray(raw)
            for i in range(0, len(flipped), 3):
                flipped[i], flipped[i + 2] = flipped[i + 2], flipped[i]
            return bytes(flipped)
        raise FormatError("bad byte_order %r" % (byte_order,), offset=None)
    width = bits // 8
    order = "little" if byte_order == "little" else "big"
    if byte_order not in ("little", "big"):
        raise FormatError("bad byte_order %r" % (byte_order,), offset=None)
    out = bytearray(width * len(samples))
    i = 0
    for sample in samples:
        value = _as_int_sample(sample, bits)
        out[i : i + width] = value.to_bytes(width, order, signed=True)
        i += width
    return bytes(out)


def unpack_pcm(data, bits=24, byte_order="little", normalized=True):
    """按位深解包样本（与 :func:`pack_pcm` 互逆）。"""
    if bits not in (8, 16, 24, 32):
        raise FormatError("unsupported bit depth %r" % (bits,), offset=None)
    width = bits // 8
    if len(data) % width:
        raise LengthMismatchError(
            "payload length %d is not a multiple of %d" % (len(data), width),
            offset=0,
            length=len(data),
        )
    if bits == 24:
        if byte_order == "little":
            return unpack24(data, normalized=normalized)
        if byte_order == "big":
            flipped = bytearray(len(data))
            for i in range(0, len(data), 3):
                flipped[i] = data[i + 2]
                flipped[i + 1] = data[i + 1]
                flipped[i + 2] = data[i]
            return unpack24(bytes(flipped), normalized=normalized)
        raise FormatError("bad byte_order %r" % (byte_order,), offset=None)
    return [
        int.from_bytes(data[i : i + width], byte_order, signed=True)
        / (float(1 << (bits - 1)) if normalized else 1.0)
        for i in range(0, len(data), width)
    ]


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def parse(data):
    """解析 WAV / RF64 / AIFF 头部，返回元数据 ``dict``。"""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("data must be bytes-like")
    if isinstance(data, memoryview):
        data = data.tobytes()
    n = len(data)
    if n < 4:
        raise TruncatedError("container header truncated", offset=n, length=n)
    magic = bytes(data[:4])
    if magic in (b"RIFF", b"RF64"):
        return _parse_riff(data, n, magic == b"RF64")
    if magic == b"FORM":
        return _parse_aiff(data, n)
    raise MagicError("unknown container magic %r" % (magic,), offset=0, magic=magic)


def _check_chunk_end(pos, size, end, cid, open_ended=False):
    """返回块数据结束位置；超界则抛出长度不符/截断错误。

    ``open_ended`` 表示 ``end`` 只是实际文件长度（RF64 尚未读到 ds64），
    此时越过末尾说明文件被截断；否则说明块长度与容器声明不一致。
    """
    data_start = pos + 8
    data_end = data_start + size
    if data_end > end:
        if open_ended:
            raise TruncatedError(
                "chunk %r declares %d bytes, file ends early"
                % (_id_text(cid), size),
                offset=end,
                chunk=cid,
                declared=size,
                available=end - data_start,
                expected=data_end,
            )
        raise LengthMismatchError(
            "%s %r length %d exceeds container boundary"
            % ("chunk", _id_text(cid), size),
            offset=pos,
            chunk=cid,
            declared=size,
            available=end - data_start,
            size_offset=pos + 4,
        )
    return data_start, data_end


def _id_text(cid):
    try:
        return cid.decode("ascii")
    except Exception:
        return repr(cid)


def _next_chunk(pos, size, data_end, end, data):
    """计算下一个块的位置，并校验偶字节填充/对齐。"""
    if not size & 1:
        return data_end
    if data_end >= end:
        # 末尾奇数字节块缺少填充字节：容器内已无字节可读，宽容处理。
        return end
    if data[data_end : data_end + 4] in _KNOWN_CHUNK_IDS:
        raise AlignmentError(
            "odd-sized chunk at offset %d is not padded" % pos,
            offset=data_end,
            chunk_offset=pos,
        )
    return data_end + 1


def _parse_riff(data, n, is_rf64):
    if n < 12:
        raise TruncatedError("RIFF header truncated", offset=n, length=n)
    riff_size = _u32le(data, 4)
    form = bytes(data[8:12])
    if form != b"WAVE":
        raise MagicError("RIFF form type %r is not WAVE" % (form,), offset=8, form=form)

    container_end = None
    if riff_size != 0xFFFFFFFF:
        container_end = riff_size + 8
        if container_end < 12:
            raise LengthMismatchError(
                "RIFF size %d is smaller than its header" % riff_size,
                offset=4,
                declared=riff_size,
            )
        if container_end > n:
            raise TruncatedError(
                "RIFF declares %d bytes but only %d available"
                % (container_end, n),
                offset=n,
                expected=container_end,
                available=n,
            )

    fmt_info = None
    data_offset = None
    data_size = 0
    ds64 = None
    pos = 12
    # RF64 在 ds64 出现前无法确定容器终点；先以实际长度为准。
    end = container_end if container_end is not None else n

    while pos + 8 <= end:
        if pos & 1:
            raise AlignmentError(
                "chunk header at odd offset %d" % pos, offset=pos
            )
        cid = bytes(data[pos : pos + 4])
        size = _u32le(data, pos + 4)
        if is_rf64 and size == 0xFFFFFFFF:
            if cid == b"data" and ds64 is not None:
                size = ds64["data_size"]
            elif cid == b"ds64" and ds64 is None:
                # ds64 自身长度不会用 0xFFFFFFFF；交给下面的长度校验。
                pass

        data_start, data_end = _check_chunk_end(
            pos, size, end, cid, open_ended=container_end is None
        )

        if cid == b"fmt ":
            if size < 16:
                raise LengthMismatchError(
                    "fmt chunk length %d is too small (need >= 16)" % size,
                    offset=pos,
                    chunk=cid,
                    declared=size,
                    available=end - data_start,
                )
            audio_format, channels, rate, _byte_rate, block_align, bits = (
                struct.unpack_from("<HHIIHH", data, data_start)
            )
            if channels == 0:
                raise FormatError(
                    "fmt chunk declares zero channels", offset=data_start
                )
            fmt_info = {
                "audio_format": audio_format,
                "channels": channels,
                "rate": rate,
                "block_align": block_align,
                "bits": bits,
            }
        elif cid == b"data":
            data_offset = data_start
            data_size = size
        elif cid == b"ds64":
            if size < 24:
                raise LengthMismatchError(
                    "ds64 chunk length %d is too small (need >= 24)" % size,
                    offset=pos,
                    chunk=cid,
                    declared=size,
                    available=end - data_start,
                )
            riff_size64, data_size64, sample_count64 = struct.unpack_from(
                "<QQQ", data, data_start
            )
            ds64 = {
                "riff_size": riff_size64,
                "data_size": data_size64,
                "sample_count": sample_count64,
            }
            if container_end is None:
                if riff_size64 != 0:
                    candidate = riff_size64 + 8
                    if candidate > n:
                        raise TruncatedError(
                            "RF64 declares %d bytes but only %d available"
                            % (candidate, n),
                            offset=n,
                            expected=candidate,
                            available=n,
                        )
                    container_end = candidate
                    end = candidate
                    if data_end > end:
                        raise LengthMismatchError(
                            "ds64 chunk exceeds RF64 boundary",
                            offset=pos,
                            chunk=cid,
                        )
        # 其余块（fact/LIST/JUNK/bext/...）一律跳过，仅做长度与对齐校验。

        pos = _next_chunk(pos, size, data_end, end, data)

    if container_end is None:
        # RF64 必须由 ds64 给出真实长度；没有读到说明文件被截断。
        raise TruncatedError(
            "RF64 container has no ds64 chunk (truncated?)",
            offset=n,
            available=n,
        )
    if fmt_info is None:
        raise MissingChunkError(
            "WAV container has no fmt chunk", offset=12
        )
    if data_offset is None:
        data_offset = end
        data_size = 0

    bits = fmt_info["bits"]
    channels = fmt_info["channels"]
    rate = fmt_info["rate"]
    block_align = fmt_info["block_align"] or (channels * bits // 8)
    frames = data_size // block_align if block_align else 0
    result = {
        "format": "rf64" if is_rf64 else "wav",
        "container": "RF64" if is_rf64 else "RIFF",
        "channels": channels,
        "rate": rate,
        "sample_rate": rate,
        "bits": bits,
        "block_align": block_align,
        "byte_order": "little",
        "encoding": "pcm" if fmt_info["audio_format"] == 1 else fmt_info["audio_format"],
        "audio_format": fmt_info["audio_format"],
        "data_offset": data_offset,
        "data_size": data_size,
        "frames": frames,
    }
    if ds64 is not None:
        result["rf64"] = dict(ds64)
    return result


def _parse_aiff(data, n):
    if n < 12:
        raise TruncatedError("FORM header truncated", offset=n, length=n)
    form_size = _u32be(data, 4)
    form = bytes(data[8:12])
    if form not in (b"AIFF", b"AIFC"):
        raise MagicError(
            "FORM form type %r is not AIFF/AIFC" % (form,), offset=8, form=form
        )
    end = form_size + 8
    if end < 12:
        raise LengthMismatchError(
            "FORM size %d is smaller than its header" % form_size,
            offset=4,
            declared=form_size,
        )
    if end > n:
        raise TruncatedError(
            "FORM declares %d bytes but only %d available" % (end, n),
            offset=n,
            expected=end,
            available=n,
        )

    channels = None
    rate = 0
    bits = 0
    frames_declared = 0
    compression = b"NONE"
    data_offset = None
    data_size = 0
    pos = 12

    while pos + 8 <= end:
        if pos & 1:
            raise AlignmentError("chunk header at odd offset %d" % pos, offset=pos)
        cid = bytes(data[pos : pos + 4])
        size = _u32be(data, pos + 4)
        data_start, data_end = _check_chunk_end(pos, size, end, cid)

        if cid == b"COMM":
            if size < 18:
                # AIFF-C 允许 COMM 带压缩类型（>= 22），但采样率字段至少到 18。
                if form == b"AIFC" and size >= 22:
                    pass
                elif size >= 8:
                    # 宽容：字段不足时取已有部分，采样率留 0，便于识别损坏样本。
                    channels = _I16BE(data, data_start)[0]
                    frames_declared = _u32be(data, data_start + 2)
                    bits = _I16BE(data, data_start + 6)[0]
                    rate = 0
                else:
                    raise LengthMismatchError(
                        "COMM chunk length %d is too small (need >= 8)" % size,
                        offset=pos,
                        chunk=cid,
                        declared=size,
                        available=end - data_start,
                    )
            else:
                channels = _I16BE(data, data_start)[0]
                frames_declared = _u32be(data, data_start + 2)
                bits = _I16BE(data, data_start + 6)[0]
                rate = decode_extended(data[data_start + 8 : data_start + 18])
                if form == b"AIFC" and size >= 22:
                    compression = bytes(data[data_start + 18 : data_start + 22])
            if channels is not None and channels <= 0:
                raise FormatError(
                    "COMM chunk declares non-positive channels", offset=data_start
                )
        elif cid == b"SSND":
            data_offset = data_start + 8 if size >= 8 else data_start
            data_size = size - 8 if size >= 8 else 0
        # 其他块跳过。

        pos = _next_chunk(pos, size, data_end, end, data)

    if channels is None:
        raise MissingChunkError("AIFF container has no COMM chunk", offset=12)
    if data_offset is None:
        data_offset = end
        data_size = 0

    block_align = channels * bits // 8
    frames = frames_declared or (data_size // block_align if block_align else 0)
    result = {
        "format": "aifc" if form == b"AIFC" else "aiff",
        "container": "FORM",
        "channels": channels,
        "rate": rate,
        "sample_rate": rate,
        "bits": bits,
        "block_align": block_align,
        "byte_order": "big",
        "encoding": "pcm",
        "compression": compression.decode("ascii", "replace"),
        "data_offset": data_offset,
        "data_size": data_size,
        "frames": frames,
    }
    return result


# ---------------------------------------------------------------------------
# 构造
# ---------------------------------------------------------------------------


def _spec_int(spec, names, default=None):
    for name in names:
        if name in spec and spec[name] is not None:
            value = spec[name]
            try:
                return int(value)
            except (TypeError, ValueError):
                raise FormatError(
                    "%s must be an integer, got %r" % (name, value), offset=None
                )
    return default


def _coerce_spec(fmt, kwargs):
    if fmt is None:
        spec = {}
    elif isinstance(fmt, dict):
        spec = dict(fmt)
    elif isinstance(fmt, str):
        spec = {"format": fmt}
    else:
        raise TypeError("fmt must be a dict or format name")
    spec.update(kwargs)
    return spec


def _packed_samples(spec, channels, bits):
    """取出可选样本数据：原始字节或浮点/整数样本序列。"""
    raw = spec.get("data")
    if raw is not None:
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise FormatError("data must be bytes-like", offset=None)
        return bytes(raw)
    samples = spec.get("samples")
    if samples is None:
        return b""
    byte_order = "big" if str(spec.get("format", "wav")).lower() in (
        "aiff",
        "aif",
        "aifc",
    ) else "little"
    return pack_pcm(samples, bits=bits, byte_order=byte_order)


def build(fmt=None, **kwargs):
    """构造容器头（默认 WAV），返回 ``bytes``。

    ``fmt`` 为 ``dict``（或格式名字符串），可含键：

    - ``rate`` / ``sample_rate``（必填，> 0）
    - ``channels``（必填，1..65535）
    - ``bits``（必填，8/16/24/32）
    - ``format`` / ``container`` / ``type``：``wav``（默认）、``rf64``、``aiff``
    - ``data``：原始 PCM 字节；或 ``samples``：浮点/整数样本序列
    """
    spec = _coerce_spec(fmt, kwargs)
    rate = _spec_int(spec, ("rate", "sample_rate"))
    channels = _spec_int(spec, ("channels", "channel"))
    bits = _spec_int(spec, ("bits", "bit_depth", "sample_size"))
    if rate is None or channels is None or bits is None:
        raise FormatError(
            "rate, channels and bits are required", offset=None
        )
    if rate <= 0 or rate > 0xFFFFFFFF:
        raise FormatError("rate must be in 1..2**32-1, got %d" % rate, offset=None)
    if channels <= 0 or channels > 0xFFFF:
        raise FormatError(
            "channels must be in 1..65535, got %d" % channels, offset=None
        )
    if bits not in (8, 16, 24, 32):
        raise FormatError(
            "bits must be one of 8/16/24/32, got %d" % bits, offset=None
        )

    name = spec.get("format", spec.get("container", spec.get("type", "wav")))
    if not isinstance(name, str):
        raise FormatError("format must be a string", offset=None)
    name = name.strip().lower()
    payload = _packed_samples(spec, channels, bits)

    if name in ("wav", "wave", "riff"):
        return _build_wav(rate, channels, bits, payload)
    if name in ("rf64",):
        return _build_rf64(rate, channels, bits, payload)
    if name in ("aiff", "aif", "aifc"):
        return _build_aiff(rate, channels, bits, payload, aifc=(name == "aifc"))
    raise FormatError("unknown format %r" % (name,), offset=None)


def _chunk_le(cid, body):
    chunk = cid + struct.pack("<I", len(body)) + body
    if len(body) & 1:
        chunk += b"\x00"
    return chunk


def _chunk_be(cid, body):
    chunk = cid + struct.pack(">I", len(body)) + body
    if len(body) & 1:
        chunk += b"\x00"
    return chunk


def _build_wav(rate, channels, bits, payload):
    block_align = channels * bits // 8
    byte_rate = rate * block_align
    fmt_body = struct.pack(
        "<HHIIHH", 1, channels, rate & 0xFFFFFFFF, byte_rate & 0xFFFFFFFF,
        block_align & 0xFFFF, bits,
    )
    body = _chunk_le(b"fmt ", fmt_body)
    if payload:
        body += _chunk_le(b"data", payload)
    else:
        body += b"data" + struct.pack("<I", 0)
    riff_size = 4 + len(body)
    return b"RIFF" + struct.pack("<I", riff_size & 0xFFFFFFFF) + b"WAVE" + body


def _build_rf64(rate, channels, bits, payload):
    block_align = channels * bits // 8
    byte_rate = rate * block_align
    fmt_body = struct.pack(
        "<HHIIHH", 1, channels, rate & 0xFFFFFFFF, byte_rate & 0xFFFFFFFF,
        block_align & 0xFFFF, bits,
    )
    fmt_chunk = _chunk_le(b"fmt ", fmt_body)
    # RF64: data 块长度字段固定为 0xFFFFFFFF，真实长度放在 ds64 中。
    data_chunk = b"data" + struct.pack("<I", 0xFFFFFFFF) + payload
    if len(payload) & 1:
        data_chunk += b"\x00"
    sample_count = len(payload) // block_align if block_align else 0
    ds64_size = 28
    riff_size = 4 + 8 + ds64_size + len(fmt_chunk) + len(data_chunk)
    ds64_body = struct.pack(
        "<QQQI", riff_size, len(payload), sample_count, 0
    )
    ds64_chunk = _chunk_le(b"ds64", ds64_body)
    body = ds64_chunk + fmt_chunk + data_chunk
    return (
        b"RF64"
        + struct.pack("<I", 0xFFFFFFFF)
        + b"WAVE"
        + body
    )


def _build_aiff(rate, channels, bits, payload, aifc=False):
    block_align = channels * bits // 8
    frames = len(payload) // block_align if block_align else 0
    comm_body = struct.pack(">hIh", channels, frames & 0xFFFFFFFF, bits)
    comm_body += encode_extended(float(rate))
    if aifc:
        comm_body += b"NONE" + b"NONE"
    comm_chunk = _chunk_be(b"COMM", comm_body)
    ssnd_body = struct.pack(">II", 0, 0) + payload
    ssnd_chunk = _chunk_be(b"SSND", ssnd_body)
    body = comm_chunk + ssnd_chunk
    form_size = 4 + len(body)
    form_type = b"AIFC" if aifc else b"AIFF"
    return b"FORM" + struct.pack(">I", form_size & 0xFFFFFFFF) + form_type + body


# ---------------------------------------------------------------------------
# 面向对象封装
# ---------------------------------------------------------------------------


class PcmParse:
    """容器解析/构造门面。"""

    def parse(self, data):
        """解析 WAV / RF64 / AIFF 头部，返回元数据 ``dict``。"""
        return parse(data)

    def build(self, fmt=None, **kwargs):
        """构造容器头，返回 ``bytes``。"""
        return build(fmt, **kwargs)

    # 便捷的 24 位打包接口（与模块级函数一致）。
    pack24 = staticmethod(pack24)
    unpack24 = staticmethod(unpack24)
    pack_pcm = staticmethod(pack_pcm)
    unpack_pcm = staticmethod(unpack_pcm)
