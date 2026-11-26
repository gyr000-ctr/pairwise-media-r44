"""aggro：仇恨表与目标选择（仅使用 Python 标准库）。

模型约定
--------
* 距离衰减增量：``inc = amount * exp(-decay * (dist - 1.0))``。``dist`` 以 1.0
  为参考距离，越远增量越小，取值范围 ``(0, +inf)``。
* 时间指数衰减：任意目标的仇恨读数为解析式
  ``v(t) = v0 * exp(-decay * (t - t0))``。实现采用惰性求值：只保存基准值与
  基准时刻，在需要时按解析式求值，因此多次 ``tick`` 不会累积舍入误差，
  与解析式的偏差仅在浮点舍入量级（远小于 1e-9），且 ``tick`` 为 O(1)。
* 溢出钳制：有效仇恨恒被钳制在 ``[0, MAX_HATE]``（默认 ``1e12``）。
* 目标选择：有效仇恨最大者；平局按首次加入顺序（先加入者胜）。
* 嘲讽：``taunt`` 立即强制切换目标，并在 ``duration`` 秒内保持；到期后恢复
  正常选择。
* 非法参数：各校验失败抛出可区分的 ``ValueError`` 子类
  （``InvalidAmount`` / ``InvalidDistance`` / ``InvalidDecay`` /
  ``InvalidTime`` / ``InvalidTarget``），且校验失败不会改动任何状态。
"""

from __future__ import annotations

import math

__all__ = [
    "Aggro",
    "MAX_HATE",
    "AggroError",
    "InvalidAmount",
    "InvalidDistance",
    "InvalidDecay",
    "InvalidTime",
    "InvalidTarget",
]

#: 单目标仇恨上限（溢出钳制阈值）。
MAX_HATE = 1e12

_INF = float("inf")


class AggroError(ValueError):
    """aggro 参数错误的基类（同时是 ValueError，便于统一捕获）。"""


class InvalidAmount(AggroError):
    """非法仇恨增量（非数值、非有限或 <= 0）。"""


class InvalidDistance(AggroError):
    """非法距离（非数值、非有限或 <= 0）。"""


class InvalidDecay(AggroError):
    """非法衰减系数（非数值、非有限或 <= 0）。"""


class InvalidTime(AggroError):
    """非法时间推进 / 嘲讽时长（非数值、非有限或 < 0）。"""


class InvalidTarget(AggroError):
    """非法目标（None 或不可哈希）。"""


def _number(value, name, exc):
    """把 *value* 规范为有限 float；失败抛出 *exc*（ValueError 子类）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise exc(f"{name} must be a real number, got {type(value).__name__}")
    value = float(value)
    if not math.isfinite(value):
        raise exc(f"{name} must be finite, got {value!r}")
    return value


def _positive(value, name, exc):
    value = _number(value, name, exc)
    if value <= 0.0:
        raise exc(f"{name} must be > 0, got {value!r}")
    return value


def _non_negative(value, name, exc):
    value = _number(value, name, exc)
    if value < 0.0:
        raise exc(f"{name} must be >= 0, got {value!r}")
    return value


def _check_target(target):
    if target is None:
        raise InvalidTarget("target must not be None")
    try:
        hash(target)
    except TypeError as exc:  # 不可哈希，不能作为字典键
        raise InvalidTarget(f"target must be hashable, got {type(target).__name__}") from exc


class Aggro:
    """仇恨表。"""

    #: 类级常量，便于外部读取钳制阈值。
    MAX_HATE = MAX_HATE

    def __init__(self, decay):
        """构造。

        :param decay: 每秒衰减系数（> 0，有限）。同时用作距离衰减的系数。
        """
        self._decay = _positive(decay, "decay", InvalidDecay)
        self._now = 0.0
        # target -> [value_at_t0, t0]
        self._entries = {}
        # 嘲讽状态
        self._taunt_target = None
        self._taunt_until = 0.0
        self._taunted = False

    # ------------------------------------------------------------------ 内部

    def _effective(self, entry, now):
        """按解析式求 ``entry`` 在时刻 *now* 的有效仇恨。"""
        value, t0 = entry
        dt = now - t0
        if dt > 0.0:
            value *= math.exp(-self._decay * dt)
        if value > MAX_HATE:
            return MAX_HATE
        if value < 0.0:
            return 0.0
        return value

    # ------------------------------------------------------------------ 公共

    def add(self, target, amount, dist):
        """向 *target* 累加一次距离衰减后的仇恨增量。

        返回该目标累加后（已钳制）的有效仇恨，类型为 ``float``。
        """
        _check_target(target)
        amount = _positive(amount, "amount", InvalidAmount)
        dist = _positive(dist, "distance", InvalidDistance)

        # 距离衰减：以 dist == 1.0 为参考，越远增量越小。
        inc = amount * math.exp(-self._decay * (dist - 1.0))

        now = self._now
        entry = self._entries.get(target)
        if entry is None:
            self._entries[target] = [0.0, now]
            entry = self._entries[target]
        else:
            entry[0] = self._effective(entry, now)
            entry[1] = now

        value = entry[0] + inc  # 溢出为 inf 时同样被钳制
        if not math.isfinite(value) or value > MAX_HATE:
            value = MAX_HATE
        entry[0] = value
        entry[1] = now
        return float(value)

    def tick(self, dt):
        """推进 *dt* 秒（惰性衰减，O(1)）。"""
        dt = _non_negative(dt, "dt", InvalidTime)
        self._now += dt
        if self._taunted and self._now >= self._taunt_until:
            self._taunted = False
            self._taunt_target = None

    def target(self):
        """当前目标：嘲讽期内为被嘲讽目标，否则为有效仇恨最大者。

        平局按加入顺序（先加入者优先）。空表返回 ``None``。
        """
        if self._taunted:
            if self._now < self._taunt_until:
                return self._taunt_target
            self._taunted = False
            self._taunt_target = None

        now = self._now
        best = None
        best_value = -_INF
        for tgt, entry in self._entries.items():
            value = self._effective(entry, now)
            if value > best_value:  # 严格大于：平局保留先加入者
                best_value = value
                best = tgt
        return best

    def taunt(self, target, duration):
        """强制切换目标并保持 *duration* 秒。"""
        _check_target(target)
        duration = _positive(duration, "duration", InvalidTime)
        self._taunt_target = target
        self._taunt_until = self._now + duration
        self._taunted = True

    def threat(self, target):
        """读取 *target* 在当前位置的有效仇恨（未加入则为 0.0）。"""
        _check_target(target)
        entry = self._entries.get(target)
        if entry is None:
            return 0.0
        return float(self._effective(entry, self._now))

    #: ``threat`` 的别名。
    hate = threat

    def taunt_remaining(self):
        """嘲讽剩余保持时间（秒）；未处于嘲讽期为 0.0。"""
        if self._taunted and self._now < self._taunt_until:
            return float(self._taunt_until - self._now)
        return 0.0

    def __len__(self):
        return len(self._entries)

    def __contains__(self, target):
        return target in self._entries
