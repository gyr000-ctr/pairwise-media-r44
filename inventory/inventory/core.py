"""inventory 核心 API：背包格子装箱（仅标准库）。

坐标约定：网格左上角为 ``(0, 0)``，``x`` 向右、``y`` 向下。

放置策略（首次适配）：
    按行优先顺序（``y`` 外层、``x`` 内层）扫描，返回第一个能容纳物品的
    左上角 ``(x, y)``；物品内部与已占用格互不重叠、不越界。若开启
    ``rotate``，先在整个网格上尝试原始朝向，仍无位置时再尝试旋转 90°
    （即旋转是兜底选项，不会改变未旋转物品的首次适配结果）。

失败语义：
    ``place`` 在无空位时返回 ``None``（不抛错），并把 ``last_failure``
    置为原因分类：``"too_large"``（空网格也放不下）或 ``"no_space"``
    （放得下但当前无空位）。非法输入（尺寸 <= 0、NaN、非整数、错误元数）
    统一抛 ``ValueError``。

最优对照：
    物品数 <= 8 时可用 :func:`optimal_used` 暴力求出该网格能达到的最大
    占用格数；任何合法放置都满足 ``used() <= optimal_used(...)``。
"""

import bisect
import math

__all__ = ["Inventory", "optimal_used", "FAIL_TOO_LARGE", "FAIL_NO_SPACE"]

FAIL_TOO_LARGE = "too_large"
FAIL_NO_SPACE = "no_space"


def _positive_int(value, what):
    """校验并归一化正整数（拒绝 bool / NaN / 非整数 / 其他类型）。"""
    if isinstance(value, bool):
        raise ValueError("%s 必须是正整数: %r" % (what, value))
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        number = int(value)
    else:
        raise ValueError("%s 必须是正整数: %r" % (what, value))
    if number <= 0:
        raise ValueError("%s 必须是正整数: %r" % (what, value))
    return number


def _parse_item(item):
    """把 ``item`` 解析为 ``(w, h)``；结构非法时抛 ``ValueError``。"""
    try:
        iw, ih = item
    except (TypeError, ValueError):
        raise ValueError("物品必须是 (宽, 高) 二元组: %r" % (item,))
    return _positive_int(iw, "物品宽度"), _positive_int(ih, "物品高度")


def _orientations(iw, ih, rotate):
    if rotate and iw != ih:
        return ((iw, ih), (ih, iw))
    return ((iw, ih),)


class Inventory:
    """二维格子背包；每行用一个整数位掩码记录占用情况。"""

    def __init__(self, w, h, rotate=False):
        self.w = _positive_int(w, "宽度")
        self.h = _positive_int(h, "高度")
        self.rotate = bool(rotate)
        self._full_mask = (1 << self.w) - 1
        self._rows = [0] * self.h
        # 尚未填满的行号（升序）。格子只会被占用，因此行一旦填满就永久移出。
        self._open_rows = list(range(self.h))
        self._used = 0
        # 首次适配的单调性缓存：占用只增不减，因此某朝向的首次可放位置
        # 只会向下移动；一旦确认放不下，就永远放不下（直到 reset）。
        self._scan_from = {}  # (ow, oh) -> 下次扫描的起始行
        self._dead = set()    # 已确认再也放不下的朝向
        #: 已放置记录，元素为 ``(x, y, w, h)``（w/h 为实际朝向）。
        self.placements = []
        #: 最近一次 ``place`` 失败的原因分类；成功或初始时为 ``None``。
        self.last_failure = None

    # ------------------------------------------------------------------ 放置
    def place(self, item):
        """按首次适配放置物品，返回左上角 ``(x, y)``；放不下返回 ``None``。"""
        iw, ih = _parse_item(item)
        self.last_failure = None

        orientations = _orientations(iw, ih, self.rotate)
        if not any(ow <= self.w and oh <= self.h for ow, oh in orientations):
            self.last_failure = FAIL_TOO_LARGE
            return None
        # 面积不够时无需扫描（所有朝向面积相同）。
        if iw * ih > self.w * self.h - self._used:
            self.last_failure = FAIL_NO_SPACE
            return None

        for ow, oh in orientations:
            key = (ow, oh)
            if key in self._dead:
                continue
            pos = self._first_fit(ow, oh, self._scan_from.get(key, 0))
            if pos is not None:
                self._scan_from[key] = pos[1]
                self._occupy(pos[0], pos[1], ow, oh)
                self.placements.append((pos[0], pos[1], ow, oh))
                return pos
            self._dead.add(key)

        self.last_failure = FAIL_NO_SPACE
        return None

    def can_place(self, item):
        """只探测不修改：是否存在可放置位置。非法输入仍抛 ``ValueError``。"""
        iw, ih = _parse_item(item)
        for ow, oh in _orientations(iw, ih, self.rotate):
            if ow <= self.w and oh <= self.h and self._first_fit(ow, oh) is not None:
                return True
        return False

    def place_all(self, items):
        """逐项放置，返回与输入等长的结果列表（成功为坐标，失败为 ``None``）。"""
        return [self.place(item) for item in items]

    def reason(self):
        """最近一次 ``place`` 失败的原因分类；成功或初始时为 ``None``。"""
        return self.last_failure

    def _first_fit(self, iw, ih, start_y=0):
        """行优先扫描第一个可容纳 ``iw x ih`` 的位置；无则 ``None``。

        位并行实现：对候选起始行区间求各空闲行掩码的交集，再用
        ``t &= t >> 1`` 找出长度为 ``iw`` 的连续空闲位。``start_y``
        用于跳过已经不可能命中的顶部行（占用只增不减，见 ``place``）。
        """
        if iw > self.w or ih > self.h or len(self._open_rows) < ih:
            return None
        rows = self._rows
        full = self._full_mask
        open_rows = self._open_rows
        extra = iw - 1
        last = len(open_rows) - ih + 1
        first = bisect.bisect_left(open_rows, start_y)
        for idx in range(first, last):
            y = open_rows[idx]
            if open_rows[idx + ih - 1] != y + ih - 1:
                continue  # 区间内存在已填满的行，无法容纳
            feasible = full
            for r in range(y, y + ih):
                feasible &= full ^ rows[r]
            t = feasible
            for _ in range(extra):
                t &= t >> 1
            if t:
                low = t & -t
                return (low.bit_length() - 1, y)
        return None

    def _occupy(self, x, y, iw, ih):
        mask = ((1 << iw) - 1) << x
        rows = self._rows
        full = self._full_mask
        for row in range(y, y + ih):
            rows[row] |= mask
            if rows[row] == full:
                self._open_rows.remove(row)
        self._used += iw * ih

    # ------------------------------------------------------------------ 查询
    def used(self):
        """已占用格数。"""
        return self._used

    def free(self):
        """剩余空格数。"""
        return self.w * self.h - self._used

    def grid(self):
        """占用图：``h`` 行 ``w`` 列，占用为 1、空闲为 0。"""
        rows = self._rows
        return [[(rows[y] >> x) & 1 for x in range(self.w)] for y in range(self.h)]

    def reset(self):
        """清空全部放置，恢复初始状态。"""
        self._rows = [0] * self.h
        self._open_rows = list(range(self.h))
        self._used = 0
        self._scan_from.clear()
        self._dead.clear()
        self.placements = []
        self.last_failure = None


def optimal_used(w, h, items, rotate=False):
    """暴力最优对照：在 ``w x h`` 网格中放置 ``items`` 能达到的最大占用格数。

    物品数限定为 <= 8（否则抛 ``ValueError``）。允许任意放置次序与位置，
    旋转遵循 ``rotate``；允许放弃部分物品（目标是被占用格数最大）。
    结果恒为任何合法放置占用格数的上界，因此先构造
    ``Inventory(w, h, rotate)`` 再 ``place_all(items)`` 后必然有
    ``used() <= optimal_used(w, h, items, rotate)``。
    """
    w = _positive_int(w, "宽度")
    h = _positive_int(h, "高度")
    parsed = [_parse_item(item) for item in items]
    if len(parsed) > 8:
        raise ValueError("暴力最优对照仅支持物品数 <= 8: %d" % len(parsed))

    full = (1 << w) - 1
    areas = [iw * ih for iw, ih in parsed]
    upper = min(w * h, sum(areas))
    # 每个物品的候选朝向（去重，保持原始朝向优先）。
    shapes = []
    for iw, ih in parsed:
        # 放不下的朝向直接剔除：这类物品在最优解里只能被放弃。
        opts = [(ow, oh) for ow, oh in _orientations(iw, ih, rotate)
                if ow <= w and oh <= h]
        shapes.append(list(dict.fromkeys(opts)))

    # 启发式下界：按“大到小”做首次适配放置，为搜索提供较高起点。
    order = sorted(range(len(parsed)), key=lambda i: -areas[i])
    probe = Inventory(w, h, rotate)
    for i in order:
        probe.place(parsed[i])
    best = probe.used()
    if best == upper:
        return best
    seen = set()

    def can_fit_covering(rows, x, y, ow, oh):
        """``ow x oh`` 是否存在某个覆盖格 ``(x, y)`` 的合法位置。

        同理用于剩余面积上界；``rows`` 中已标记的格子（含搜索中跳过的
        格子）视为不可用。
        """
        y_lo = max(0, y - oh + 1)
        y_hi = min(y, h - oh)
        x_lo = max(0, x - ow + 1)
        x_hi = min(x, w - ow)
        if y_lo > y_hi or x_lo > x_hi:
            return False
        base = (1 << ow) - 1
        for py in range(y_lo, y_hi + 1):
            span = rows[py:py + oh]
            for px in range(x_lo, x_hi + 1):
                mask = base << px
                if not any(row & mask for row in span):
                    return True
        return False

    def fit_area(remaining, rows, x, y):
        """剩余物品中存在某朝向能覆盖 ``(x, y)`` 的面积之和（可采纳上界）。"""
        total = 0
        for idx in remaining:
            for ow, oh in shapes[idx]:
                if can_fit_covering(rows, x, y, ow, oh):
                    total += areas[idx]
                    break
        return total

    def rec(remaining, rows, used):
        nonlocal best
        if used > best:
            best = used
            if best == upper:
                return
        if not remaining:
            return
        # 行优先找到第一个空格；任何打包要么覆盖它，要么跳过它。
        for y in range(h):
            free = full ^ rows[y]
            if free:
                x = (free & -free).bit_length() - 1
                break
        else:
            return
        if used + fit_area(remaining, rows, x, y) <= best:
            return
        if (remaining, rows) in seen:
            return
        seen.add((remaining, rows))

        # 先尝试覆盖该格（更容易尽快抬高 best），再尝试跳过。
        tried_shapes = set()
        for pos, idx in enumerate(remaining):
            if not shapes[idx]:
                continue
            shape_key = shapes[idx][0]  # 同一物品的朝向集合相同，可去重
            if shape_key in tried_shapes:
                continue
            tried_shapes.add(shape_key)
            rest = remaining[:pos] + remaining[pos + 1:]
            for ow, oh in shapes[idx]:
                base = (1 << ow) - 1
                x_lo = max(0, x - ow + 1)
                x_hi = min(x, w - ow)
                y_lo = max(0, y - oh + 1)
                y_hi = min(y, h - oh)
                for py in range(y_lo, y_hi + 1):
                    span = rows[py:py + oh]
                    for px in range(x_lo, x_hi + 1):
                        mask = base << px
                        if any(row & mask for row in span):
                            continue
                        new_rows = list(rows)
                        for r in range(py, py + oh):
                            new_rows[r] |= mask
                        rec(rest, tuple(new_rows), used + ow * oh)
        # 跳过：把该格标记为不可用（不增加占用）。
        skip_rows = list(rows)
        skip_rows[y] |= 1 << x
        rec(remaining, tuple(skip_rows), used)

    rec(tuple(range(len(parsed))), (0,) * h, 0)
    return best
