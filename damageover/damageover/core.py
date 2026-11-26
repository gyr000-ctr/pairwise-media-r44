"""damageover 核心 API（仅使用 Python 标准库）。

结算模型
--------
每个 DOT 效果独立维护：剩余时长 ``remaining``、当前 tick 周期内累计时间
``acc``、已结算跳数 ``ticks``。``update(dt)`` 按效果的施加顺序依次结算，
各效果互不影响（一个效果到期不会改变其他效果的推进量）。

- 固定 tick 间隔：``acc`` 累计满一个 ``tick`` 就结算一跳完整伤害
  ``dps * tick``；
- 末跳按比例：效果到期时若 ``acc`` 还有剩余（不足一个间隔），按
  ``dps * acc`` 结算一笔比例伤害；
- 因此总跳数为 ``ceil(dur / tick)``（时长恰为间隔整数倍时无比例末跳），
  总伤害在数值精度内等于 ``dps * dur``；
- 同名效果再次 ``apply`` 视为刷新：默认保留已结算跳数与 tick 进度，
  仅更新 dps 并把剩余时长重置为新的完整时长；构造时传
  ``reset_on_refresh=True`` 可改为重置进度。
"""

import math

__all__ = [
    "Dot",
    "DotError",
    "InvalidTickError",
    "InvalidDpsError",
    "InvalidDurationError",
    "InvalidDeltaError",
]


class DotError(ValueError):
    """DOT 模块所有错误的基类（本身仍是 ValueError，可区分捕获）。"""


class InvalidTickError(DotError):
    """非法 tick 间隔（非数值、非有限值或 <= 0）。"""


class InvalidDpsError(DotError):
    """非法 DPS（非数值、非有限值或负数）。"""


class InvalidDurationError(DotError):
    """非法持续时间（非数值、非有限值或 <= 0）。"""


class InvalidDeltaError(DotError):
    """非法推进时长 dt（非数值、非有限值或负数）。"""


def _finite(value, exc):
    """校验为有限实数并返回 float；失败时抛指定的可区分异常。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise exc("expected a real number, got %r" % (value,))
    if math.isnan(value) or math.isinf(value):
        raise exc("value must be finite, got %r" % (value,))
    return float(value)


class _Effect:
    """单个活跃 DOT 效果的运行时状态。"""

    __slots__ = ("name", "dps", "remaining", "acc", "ticks")

    def __init__(self, name, dps, remaining):
        self.name = name
        self.dps = dps
        self.remaining = remaining
        self.acc = 0.0
        self.ticks = 0


class Dot:
    """固定 tick 间隔的持续伤害结算器。"""

    def __init__(self, tick, reset_on_refresh=False):
        """``tick`` 为固定结算间隔（秒），必须为正的有限实数。

        ``reset_on_refresh=True`` 时，同名效果刷新会重置 tick 进度与
        已结算跳数；默认 ``False``，刷新不重置已结算跳数。
        """
        interval = _finite(tick, InvalidTickError)
        if interval <= 0.0:
            raise InvalidTickError(
                "tick interval must be > 0, got %r" % (tick,)
            )
        self.tick = interval
        self.reset_on_refresh = bool(reset_on_refresh)
        # 施加顺序的活跃效果列表；name -> _Effect 的索引；
        # name -> 累计伤害（效果到期或刷新后仍然保留）。
        self._effects = []
        self._index = {}
        self._totals = {}

    def apply(self, name, dps, dur):
        """施加（或刷新）一个名为 ``name`` 的 DOT。

        - ``dps`` 必须为非负有限实数；
        - ``dur`` 必须为正的有限实数；
        - 同名效果尚在活跃时按刷新处理（见构造参数说明）。
        """
        dps_value = _finite(dps, InvalidDpsError)
        if dps_value < 0.0:
            raise InvalidDpsError("dps must be >= 0, got %r" % (dps,))
        duration = _finite(dur, InvalidDurationError)
        if duration <= 0.0:
            raise InvalidDurationError(
                "duration must be > 0, got %r" % (dur,)
            )

        effect = self._index.get(name)
        if effect is None:
            effect = _Effect(name, dps_value, duration)
            self._effects.append(effect)
            self._index[name] = effect
            self._totals.setdefault(name, 0.0)
        else:
            # 刷新：更新 dps 并给满新时长；默认保留 tick 进度与已结算跳数。
            effect.dps = dps_value
            effect.remaining = duration
            if self.reset_on_refresh:
                effect.acc = 0.0
                effect.ticks = 0
        return None

    def update(self, dt):
        """推进 ``dt`` 秒并结算期间发生的所有跳数。

        按施加顺序处理各 DOT，效果之间互不影响。返回本次结算事件列表
        ``[(name, damage), ...]``（无结算时为空列表，绝不会是 None）。
        """
        delta = _finite(dt, InvalidDeltaError)
        if delta < 0.0:
            raise InvalidDeltaError("dt must be >= 0, got %r" % (dt,))

        tick = self.tick
        events = []
        expired = None

        for effect in self._effects:
            # 每个效果只推进自己剩余时长以内的部分，到期即止，互不影响。
            elapsed = delta if delta < effect.remaining else effect.remaining
            effect.remaining -= elapsed
            effect.acc += elapsed

            # 完整跳：相对容差吸收浮点误差，避免恰为整数倍时漏跳。
            n = int(effect.acc / tick + 1e-12)
            if n:
                damage = effect.dps * tick * n
                effect.acc -= tick * n
                if effect.acc < 0.0:
                    effect.acc = 0.0
                effect.ticks += n
                self._totals[effect.name] += damage
                events.append((effect.name, damage))

            # 到期判定：浮点减法可能残留极小正值（如 0.3-0.1*3），
            # 用相对机器精度的容差收敛到 0，保证效果必定到期。
            if effect.remaining <= 1e-12 * max(1.0, effect.acc, tick):
                effect.remaining = 0.0

            # 到期：不足一个间隔的末跳按剩余时间比例结算。
            if effect.remaining == 0.0:
                if effect.acc > 0.0:
                    damage = effect.dps * effect.acc
                    effect.ticks += 1
                    self._totals[effect.name] += damage
                    events.append((effect.name, damage))
                if expired is None:
                    expired = []
                expired.append(effect)

        if expired:
            dead = set(id(e) for e in expired)
            for effect in expired:
                del self._index[effect.name]
            self._effects = [e for e in self._effects if id(e) not in dead]

        return events

    def active(self):
        """返回当前活跃 DOT 名称列表，顺序与施加顺序一致。"""
        return [effect.name for effect in self._effects]

    def total(self, name):
        """返回 ``name`` 的累计伤害（float）；从未施加过返回 0.0。"""
        return float(self._totals.get(name, 0.0))

    def tick_count(self, name):
        """返回 ``name`` 当前活跃效果已结算的跳数；不活跃返回 0。"""
        effect = self._index.get(name)
        return effect.ticks if effect is not None else 0
