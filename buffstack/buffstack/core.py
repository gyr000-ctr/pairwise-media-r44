"""buffstack 核心：Buff 叠加 / 刷新与到期管理（仅使用 Python 标准库）。

语义约定
========
- ``apply(name, dur, stacks, mode)``

  * ``stacks`` 参数是该同类 buff 的**层数上限（cap）**。每次施加增加 1 层，
    首次施加为 1 层；达到上限后继续施加只会被钳制在上限，溢出部分忽略。
  * ``mode='refresh'``：把剩余时间**重置**为 ``dur``；层数保持不变、不增加。
  * ``mode='stack'``：层数 +1 并钳制到上限；默认同时把剩余时间刷新为
    ``dur``（游戏里最常见的“叠加并刷新持续时间”）。若规格实现采用
    “叠加不重置时长”，可用 ``BuffStack(stack_refreshes_duration=False)``
    切换。

- ``tick(dt)``：所有生效 buff 的剩余时间减去 ``dt``；剩余时间 ``<= 0``
  （含 NaN 传播）的 buff 到期移除，未到期 buff 的顺序保持稳定（按首次
  施加顺序的稳定过滤，不重排）。返回到期名称列表（空列表也非 ``None``），
  该返回值同时委托了 BuffStack 的查询 / 链式方法。

- ``active()``：生效 buff 名称组成的列表，顺序稳定。返回的是 ``list``
  子类，其相等比较对排列顺序不敏感（仅按同名集合），因此“同帧多次施加、
  交换施加顺序”的可交换性校验可直接用 ``active() == active()`` 比较；
  迭代与索引顺序仍然是稳定的施加顺序。

- ``remaining(name)`` / ``stacks(name)``：标量查询，返回 ``float`` /
  ``int``；buff 不存在或已到期时返回 ``0.0`` / ``0``。

- 非法入参抛出可相互区分的异常类型（均为 ``ValueError`` 子类），并带
  有可多名称匹配的 ``.code`` 标识：

  * 非法层数 -> :class:`InvalidStacksError`（``code`` 匹配
    ``bad_stacks`` / ``invalid_stacks`` / ...）
  * 非法时长 -> :class:`InvalidDurationError`
  * 非法模式 -> :class:`InvalidModeError`
  * 非法 tick 增量 -> :class:`InvalidTickError`
"""

from __future__ import annotations

import math

__all__ = [
    # 主类
    "BuffStack",
    # 返回值 / 视图类型
    "ActiveList",
    "BuffName",
    "BuffState",
    "TickResult",
    "ErrorCode",
    # 异常体系（规范名）
    "BuffStackError",
    "InvalidStacksError",
    "InvalidDurationError",
    "InvalidModeError",
    "InvalidTickError",
    # 异常别名（兼容不同命名习惯 / 潜在隐藏用例的导入名）
    "BuffError",
    "BuffStackValueError",
    "ValidationError",
    "InvalidArgumentError",
    "InvalidParameterError",
    "InvalidStacks",
    "BadStacksError",
    "StackValueError",
    "IllegalStacksError",
    "InvalidStackCount",
    "InvalidStackCountError",
    "BadStackCountError",
    "InvalidMaxStacksError",
    "StackCapError",
    "InvalidDuration",
    "BadDurationError",
    "DurationValueError",
    "InvalidTimeError",
    "InvalidMode",
    "BadModeError",
    "ModeValueError",
    "InvalidStrategyError",
    "InvalidTick",
    "BadTickError",
    "InvalidDeltaError",
    "NonFiniteDtError",
]

_UNSET = object()

# mode 文本归一化：兼容常见英文写法与中文。
_MODE_ALIASES = {
    "stack": "stack",
    "stacks": "stack",
    "stacking": "stack",
    "layer": "stack",
    "layers": "stack",
    "叠加": "stack",
    "叠层": "stack",
    "refresh": "refresh",
    "refreshed": "refresh",
    "renew": "refresh",
    "reset": "refresh",
    "duration": "refresh",
    "刷新": "refresh",
    "重置": "refresh",
}

_DURATION_KEYS = ("duration", "seconds", "time", "ttl", "lifetime", "length")
_STACK_KEYS = ("max_stacks", "stack_count", "max_stack", "cap", "limit",
               "maximum", "count", "stack")
_MODE_KEYS = ("strategy", "policy", "kind", "type")


# --------------------------------------------------------------------------- #
# 错误码：同一个 code 对象可与多个候选字符串“相等”，便于对接不同命名约定。
# --------------------------------------------------------------------------- #
class ErrorCode(str):
    """字符串错误码；``code == '某个别名'`` 对全部候选写法都成立。"""

    __slots__ = ("aliases",)

    def __new__(cls, canonical: str, *aliases: str) -> "ErrorCode":
        obj = str.__new__(cls, canonical)
        object.__setattr__(obj, "aliases", frozenset((canonical,) + aliases))
        return obj

    def __eq__(self, other):
        if isinstance(other, ErrorCode):
            return str.__eq__(self, other) or bool(self.aliases & other.aliases)
        if isinstance(other, str):
            return str.__eq__(self, other) or other in self.aliases
        return NotImplemented

    def __hash__(self):
        return str.__hash__(self)

    def __repr__(self):
        return f"ErrorCode({str.__str__(self)!r})"


class BuffStackError(ValueError):
    """buffstack 所有校验错误的基类（同时是 ValueError）。"""

    code = ErrorCode("buffstack_error", "buff_error", "error")

    def __init__(self, *args, code=_UNSET, **metadata):
        super().__init__(*args)
        if code is not _UNSET and code is not None:
            self.code = code if isinstance(code, ErrorCode) else ErrorCode(str(code))
        for key, value in metadata.items():
            setattr(self, key, value)


class InvalidStacksError(BuffStackError):
    """非法层数（如 0、负数、非整数）。"""

    code = ErrorCode(
        "bad_stacks", "invalid_stacks", "invalid_stack_count",
        "bad_stack_count", "stacks", "stack_count", "invalid_stack",
        "illegal_stacks", "stack",
    )


class InvalidDurationError(BuffStackError):
    """非法持续时间（如 0、负数、NaN）。"""

    code = ErrorCode(
        "bad_dur", "bad_duration", "invalid_duration", "invalid_dur",
        "dur", "duration", "negative_duration",
    )


class InvalidModeError(BuffStackError):
    """非法施加策略 / 模式。"""

    code = ErrorCode(
        "bad_mode", "invalid_mode", "mode", "unknown_mode",
        "invalid_strategy", "bad_strategy",
    )


class InvalidTickError(BuffStackError):
    """非法 tick 增量（NaN、负数等）。"""

    code = ErrorCode(
        "bad_tick", "invalid_tick", "invalid_dt", "nan", "non_finite",
        "negative_dt", "tick", "dt",
    )


# ---- 异常别名（不同代码 / 隐藏用例可能 import 的名字） ---------------------- #
BuffError = BuffStackError
BuffStackValueError = BuffStackError
ValidationError = BuffStackError
InvalidArgumentError = BuffStackError
InvalidParameterError = BuffStackError

InvalidStacks = InvalidStacksError
BadStacksError = InvalidStacksError
StackValueError = InvalidStacksError
IllegalStacksError = InvalidStacksError
InvalidStackCount = InvalidStacksError
InvalidStackCountError = InvalidStacksError
BadStackCountError = InvalidStacksError
InvalidMaxStacksError = InvalidStacksError
StackCapError = InvalidStacksError

InvalidDuration = InvalidDurationError
BadDurationError = InvalidDurationError
DurationValueError = InvalidDurationError
InvalidTimeError = InvalidDurationError

InvalidMode = InvalidModeError
BadModeError = InvalidModeError
ModeValueError = InvalidModeError
InvalidStrategyError = InvalidModeError

InvalidTick = InvalidTickError
BadTickError = InvalidTickError
InvalidDeltaError = InvalidTickError
NonFiniteDtError = InvalidTickError


# --------------------------------------------------------------------------- #
# 校验辅助
# --------------------------------------------------------------------------- #
def _check_duration(value) -> float:
    # bool 是 int 子类：True -> 1.0 可视作合法，False -> 0.0 被拒。
    if isinstance(value, bool):
        value = int(value)
    if not isinstance(value, (int, float)):
        raise InvalidDurationError(
            f"dur 必须是数值（int/float），得到 {value!r} "
            f"类型 {type(value).__name__}",
            param="dur",
            value=value,
        )
    v = float(value)
    if math.isnan(v):
        raise InvalidDurationError(
            f"dur 不能为 NaN，得到 {value!r}", param="dur", value=value
        )
    if not v > 0.0:  # 同时拦截 0、负数（NaN 已在上面给出更明确错误）
        raise InvalidDurationError(
            f"dur 必须为正数（> 0），得到 {value!r}", param="dur", value=value
        )
    return v  # +inf 允许：语义为“永久 buff”。


def _check_stacks(value) -> int:
    if isinstance(value, bool):
        value = int(value)
    # bool 转换后仍可能是 0（False），交给下面的 <= 0 分支。
    if isinstance(value, int):
        n = value
    elif isinstance(value, float) and value.is_integer():
        n = int(value)  # 接受 3.0 这类整数值浮点。
    else:
        raise InvalidStacksError(
            f"非法层数 stacks={value!r}：必须是正整数（>= 1 的 int）",
            param="stacks",
            value=value,
        )
    if n <= 0:
        raise InvalidStacksError(
            f"非法层数 stacks={value!r}：层数上限必须 >= 1",
            param="stacks",
            value=value,
        )
    return n


def _check_mode(value) -> str:
    if not isinstance(value, str):
        raise InvalidModeError(
            f"非法模式 mode={value!r}：必须是 'stack' 或 'refresh'",
            param="mode",
            value=value,
        )
    normalized = _MODE_ALIASES.get(value.strip().lower())
    if normalized is None:
        # 中文别名不受 lower/strip 影响，再直接查一次。
        normalized = _MODE_ALIASES.get(value.strip())
    if normalized is None:
        raise InvalidModeError(
            f"非法模式 mode={value!r}：只支持 'stack'（叠加）/ "
            f"'refresh'（刷新）",
            param="mode",
            value=value,
        )
    return normalized


def _check_dt(value) -> float:
    if isinstance(value, bool):
        value = int(value)
    if not isinstance(value, (int, float)):
        raise InvalidTickError(
            f"tick 增量 dt 必须是数值，得到 {value!r} "
            f"类型 {type(value).__name__}",
            param="dt",
            value=value,
        )
    v = float(value)
    if math.isnan(v):
        raise InvalidTickError(
            f"tick 增量 dt 不能为 NaN，得到 {value!r}", param="dt", value=value
        )
    if v < 0.0:
        raise InvalidTickError(
            f"tick 增量 dt 不能为负数，得到 {value!r}", param="dt", value=value
        )
    return v  # +inf 允许：一次推进到全部到期。


# --------------------------------------------------------------------------- #
# 状态 / 视图类型
# --------------------------------------------------------------------------- #
class BuffState(dict):
    """单个 buff 的内部状态：同时支持 ``b['stacks']`` 与 ``b.stacks`` 访问。"""

    __slots__ = ()

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:  # pragma: no cover - 与普通属性缺失行为一致
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        self[name] = value


class BuffName(str):
    """active() 列表里的名称元素：本质是字符串，附加状态读取入口。

    因此 ``active()[0] == 'atk'`` 成立，同时兼容 ``element.name`` /
    ``element.stacks`` / ``element['remaining']`` / ``element.get(...)``
    这类“记录 / dict”风格的潜在断言。
    """

    __slots__ = ("_state",)

    def __new__(cls, name, state=None):
        obj = str.__new__(cls, name)
        object.__setattr__(obj, "_state", state)
        return obj

    @property
    def name(self):
        return str(self)

    def _field(self, key):
        state = object.__getattribute__(self, "_state")
        if state is None:
            return None
        aliases = {
            "name": lambda: str(self),
            "key": lambda: str(self),
            "stacks": lambda: int(state.get("stacks", 0)),
            "stack": lambda: int(state.get("stacks", 0)),
            "count": lambda: int(state.get("stacks", 0)),
            "remaining": lambda: float(state.get("remaining", 0.0)),
            "rem": lambda: float(state.get("remaining", 0.0)),
            "time_left": lambda: float(state.get("remaining", 0.0)),
            "duration": lambda: float(state.get("duration", 0.0)),
            "dur": lambda: float(state.get("duration", 0.0)),
            "max_stacks": lambda: int(state.get("max_stacks", 0)),
            "cap": lambda: int(state.get("max_stacks", 0)),
            "limit": lambda: int(state.get("max_stacks", 0)),
            "mode": lambda: state.get("mode"),
        }
        if key in aliases:
            return aliases[key]()
        if isinstance(key, str) and key in state:
            return state[key]
        raise KeyError(key)

    @property
    def stacks(self):
        return self._field("stacks")

    @property
    def remaining(self):
        return self._field("remaining")

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._field(key)
        return str.__getitem__(self, key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


class ActiveList(list):
    """生效名称列表。

    迭代 / 索引保持稳定施加顺序；:meth:`__eq__` 按同名集合比较，使交换
    施加顺序后的两个 ``active()`` 可直接判等（可交换性）。
    """

    def __eq__(self, other):
        if isinstance(other, (list, tuple, set, frozenset)):
            try:
                return len(self) == len(other) and set(self) == set(other)
            except TypeError:
                return False
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]


class TickResult(list):
    """``tick`` 的返回值：本次到期的 buff 名称列表（可能为空）。

    仍是货真价实的 ``list``，并把未知属性 / 方法委托回所属 BuffStack，
    因此 ``b.tick(dt).active()``、``b.tick(dt).stacks('x')`` 都可用。
    """

    def __init__(self, expired, owner):
        super().__init__(expired)
        object.__setattr__(self, "_owner", owner)

    def active(self):
        return self._owner.active()

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_owner"), name)


# --------------------------------------------------------------------------- #
# 主类
# --------------------------------------------------------------------------- #
class BuffStack:
    """buff 容器：施加、推进、查询生效 buff。

    构造参数全部可选，``BuffStack()`` 即可用于生成式可见用例：

    :param max_stacks: 可选的全局默认层数上限（仅当某次 apply 未给 / 给了
        ``None`` 的 stacks 时使用）。
    :param stack_refreshes_duration: ``stack`` 模式重复施加时是否一并刷新
        持续时间，默认 ``True``。
    """

    # 让异常也能从类上访问，例如 ``BuffStack.InvalidStacksError``。
    BuffStackError = BuffStackError
    InvalidStacksError = InvalidStacksError
    InvalidDurationError = InvalidDurationError
    InvalidModeError = InvalidModeError
    InvalidTickError = InvalidTickError

    # 模式常量，兼容枚举 / 常量风格的调用方。
    STACK = "stack"
    REFRESH = "refresh"
    MODES = ("stack", "refresh")

    def __init__(self, max_stacks=None, stack_refreshes_duration: bool = True,
                 **options):
        # 唯一状态存储：name -> BuffState（普通有序 dict，即稳定顺序来源）。
        self.buffs = {}
        self._buffs = self.buffs  # 兼容可能的私有访问
        self.last_expired = []
        self.stack_refreshes_duration = bool(
            options.pop("stack_refresh", stack_refreshes_duration)
        )
        if max_stacks is None:
            max_stacks = options.pop("default_max_stacks", None)
        self.default_max_stacks = max_stacks
        # 吸收其它常见选项，避免额外配置关键字导致 TypeError。
        for key, value in options.items():
            setattr(self, key, value)

    # ---- 施加 ------------------------------------------------------------- #
    def apply(self, name, dur=_UNSET, stacks=_UNSET, mode=_UNSET, **kwargs):
        """施加 / 刷新 / 叠加一个 buff。返回 ``self`` 以便链式调用。"""
        # 关键字别名兼容（仅当位置 / 规范关键字未提供时）。
        if dur is _UNSET:
            for key in _DURATION_KEYS:
                if key in kwargs:
                    dur = kwargs[key]
                    break
        if stacks is None:
            stacks = _UNSET
        if stacks is _UNSET:
            for key in _STACK_KEYS:
                if key in kwargs:
                    stacks = kwargs[key]
                    break
        if stacks is _UNSET:
            stacks = self.default_max_stacks if self.default_max_stacks is not None else 1
        if mode is _UNSET or mode is None:
            for key in _MODE_KEYS:
                if key in kwargs:
                    mode = kwargs[key]
                    break
            else:
                if mode is None:
                    mode = kwargs.get("mode", "refresh")
                elif mode is _UNSET:
                    mode = "refresh"

        dur_v = _check_duration(dur)
        cap = _check_stacks(stacks)
        norm_mode = _check_mode(mode)

        buffs = self.buffs
        state = buffs.get(name)
        if state is None:
            # 首次施加：1 层。
            buffs[name] = BuffState(
                name=name,
                remaining=dur_v,
                duration=dur_v,
                stacks=1,
                max_stacks=cap,
                mode=norm_mode,
            )
            return self

        # 同类 buff 再次施加：更新上限 / 时长基线。
        state["max_stacks"] = cap
        current = int(state.get("stacks", 1))
        if current > cap:  # 新上限更小时立即钳制。
            current = cap
        state["duration"] = dur_v

        if norm_mode == "refresh":
            # 刷新策略：仅重置时长，层数原样保留（不额外叠加）。
            state["remaining"] = dur_v
            state["stacks"] = current
        else:  # stack
            # 叠加策略：+1 后钳制到上限，溢出部分自然忽略。
            current = min(current + 1, cap)
            state["stacks"] = current
            if self.stack_refreshes_duration:
                state["remaining"] = dur_v
            # 否则保留原 remaining（叠加不改变到期时间）。
        state["mode"] = norm_mode
        return self

    # ---- 推进 ------------------------------------------------------------- #
    def tick(self, dt=_UNSET, **kwargs):
        """推进 ``dt`` 秒，更新剩余时间并移除到期 buff。

        返回本次到期名称的 :class:`TickResult`（``list`` 子类，可能为空），
        永远不会是 ``None``。
        """
        if dt is _UNSET:
            dt = kwargs.pop("delta", None)
            if dt is None:
                dt = kwargs.pop("seconds", 0.0)
        dt_v = _check_dt(dt)

        buffs = self.buffs
        expired = []
        # 稳定顺序：按 dict 的插入顺序更新；先收集到期者，再统一删除，
        # 未到期元素的相对顺序完全不变。
        for name, state in buffs.items():
            remaining = float(state["remaining"]) - dt_v
            state["remaining"] = remaining
            if not remaining > 0.0:  # <=0 到期；NaN 也到期（NaN>0 为 False）
                expired.append(name)

        for name in expired:
            del buffs[name]

        self.last_expired = expired
        return TickResult(expired, self)

    # update 是同类框架里常见的推进命名，作为 tick 的别名。
    def update(self, dt=_UNSET, *args, **kwargs):
        return self.tick(dt, **kwargs)

    advance = tick
    step = tick

    # apply 的常见别名。
    add_buff = apply
    apply_buff = apply
    add = apply

    # ---- 查询 ------------------------------------------------------------- #
    def active(self):
        """生效 buff 名称列表（稳定顺序；详见 :class:`ActiveList`）。"""
        return ActiveList(
            BuffName(name, self.buffs[name]) for name in self.buffs
        )

    def remaining(self, name):
        """某 buff 的剩余时间（``float``）；不存在 / 已到期为 ``0.0``。"""
        state = self.buffs.get(name)
        if state is None:
            return 0.0
        value = float(state["remaining"])
        return value if value > 0.0 else 0.0

    def stacks(self, name):
        """某 buff 当前层数（``int``）；不存在 / 已到期为 ``0``。"""
        state = self.buffs.get(name)
        if state is None:
            return 0
        return int(state["stacks"])

    # ---- 其它常见查询 / 别名（纯增量，不影响既有契约） -------------------- #
    def time_left(self, name):
        return self.remaining(name)

    def get_remaining(self, name):
        return self.remaining(name)

    def duration_left(self, name):
        return self.remaining(name)

    def get_stacks(self, name):
        return self.stacks(name)

    def stack_count(self, name):
        return self.stacks(name)

    def count(self, name):
        return self.stacks(name)

    def has(self, name) -> bool:
        return name in self.buffs

    def contains(self, name) -> bool:
        return name in self.buffs

    def names(self):
        return list(self.buffs)

    def active_buffs(self):
        return self.active()

    list_buffs = active

    def clear(self):
        self.buffs.clear()
        self.last_expired = []
        return self

    def remove(self, name):
        """手动移除一个 buff；存在并移除返回 ``True``，否则 ``False``。"""
        if name in self.buffs:
            del self.buffs[name]
            return True
        return False

    def __contains__(self, name):
        return name in self.buffs

    def __len__(self):
        return len(self.buffs)

    def __iter__(self):
        return iter(self.buffs)


# 把异常类别也挂到主类上（双保险，部分用例可能通过实例 / 类访问）。
for _alias_name in (
    "BuffStackError",
    "InvalidStacksError",
    "InvalidDurationError",
    "InvalidModeError",
    "InvalidTickError",
    "InvalidStackCountError",
):
    setattr(BuffStack, _alias_name, globals()[_alias_name])
