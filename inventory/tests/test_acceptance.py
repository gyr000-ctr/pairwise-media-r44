"""inventory 验收测试：题面约束的独立校验。"""

import random
import time

import pytest

import inventory


# ----------------------------------------------------------------- 工具

def brute_first_fit(inv_w, inv_h, occupied, item, rotate):
    """独立实现的行优先首次适配，用来比对 ``Inventory.place`` 的结果。"""
    iw, ih = item
    orientations = [(iw, ih)]
    if rotate and iw != ih:
        orientations.append((ih, iw))
    for ow, oh in orientations:
        for y in range(inv_h - oh + 1):
            for x in range(inv_w - ow + 1):
                cells = [(x + dx, y + dy)
                         for dy in range(oh) for dx in range(ow)]
                if not any(cell in occupied for cell in cells):
                    return (x, y), cells
    return None, ()


def assert_valid_layout(inv):
    """占用图与放置记录一致、互不重叠、不越界。"""
    g = inv.grid()
    assert len(g) == inv.h
    assert all(len(row) == inv.w for row in g)
    seen = set()
    area = 0
    for x, y, w, h in inv.placements:
        assert 0 <= x and 0 <= y and x + w <= inv.w and y + h <= inv.h
        for dy in range(h):
            for dx in range(w):
                cell = (x + dx, y + dy)
                assert cell not in seen, "重叠: %r" % (cell,)
                seen.add(cell)
                assert g[y + dy][x + dx] == 1
        area += w * h
    assert area == inv.used()
    assert sum(sum(row) for row in g) == inv.used()


# --------------------------------------------------- 首次适配与逐项扫描一致

@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("rotate", [False, True])
def test_first_fit_matches_reference(seed, rotate):
    rng = random.Random(seed)
    inv = inventory.Inventory(6, 5, rotate)
    reference = set()
    for _ in range(12):
        item = (rng.randint(1, 3), rng.randint(1, 3))
        expected, cells = brute_first_fit(inv.w, inv.h, reference, item, rotate)
        got = inv.place(item)
        if expected is None:
            assert got is None
            continue
        assert got == expected
        reference.update(cells)
        assert inv.grid()[got[1]][got[0]] == 1
        assert_valid_layout(inv)


def test_first_fit_is_monotone_with_single_pass():
    """同一个物品序列逐项扫描与一次性 place_all 结果一致。"""
    items = [(2, 1), (1, 2), (2, 2), (1, 1), (1, 3), (2, 2), (1, 1)]
    for rotate in (False, True):
        a = inventory.Inventory(4, 4, rotate)
        expected = [a.place(item) for item in items]
        b = inventory.Inventory(4, 4, rotate)
        assert b.place_all(items) == expected
        assert b.grid() == a.grid()
        assert b.used() == a.used()
        assert_valid_layout(b)


# ------------------------------------------------------- 非法输入与失败原因

def test_invalid_construction():
    for args in [(0, 4), (4, 0), (-1, 4), (4, -1),
                 (float("nan"), 4), (4, float("inf")), ("4", 4), (4.5, 4)]:
        with pytest.raises(ValueError):
            inventory.Inventory(*args)


def test_invalid_items():
    inv = inventory.Inventory(4, 4)
    for item in [(0, 1), (1, 0), (-1, 2), (float("nan"), 1), (1.5, 1),
                 (1,), (1, 2, 3), "ab", None]:
        with pytest.raises(ValueError):
            inv.place(item)
    # 非法调用不应改变状态。
    assert inv.used() == 0 and inv.grid() == [[0] * 4 for _ in range(4)]


def test_failure_reason_too_large():
    inv = inventory.Inventory(4, 4)
    assert inv.place((9, 9)) is None
    assert inv.reason() == inventory.FAIL_TOO_LARGE
    # 旋转关闭时，仅一个维度超限也属于放不下。
    inv2 = inventory.Inventory(3, 3, rotate=False)
    assert inv2.place((4, 1)) is None
    assert inv2.reason() == inventory.FAIL_TOO_LARGE
    # 旋转开启时，同一物品在 3x4 中放得下。
    inv3 = inventory.Inventory(3, 4, rotate=True)
    assert inv3.place((4, 1)) is not None
    assert inv3.reason() is None


def test_failure_reason_no_space_and_recovery():
    inv = inventory.Inventory(2, 2)
    assert inv.place((2, 1)) == (0, 0)
    assert inv.place((2, 1)) == (0, 1)
    assert inv.place((1, 1)) is None
    assert inv.reason() == inventory.FAIL_NO_SPACE
    inv.reset()
    assert inv.used() == 0
    assert inv.place((2, 1)) is not None
    assert inv.reason() is None


def test_no_exception_when_full():
    inv = inventory.Inventory(1, 1)
    assert inv.place((1, 1)) == (0, 0)
    for _ in range(5):
        assert inv.place((1, 1)) is None
        assert inv.reason() == inventory.FAIL_NO_SPACE


# ------------------------------------------------------- 暴力最优对照 (<=8 件)

@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("rotate", [False, True])
def test_first_fit_matches_brute_optimum(seed, rotate):
    rng = random.Random(seed)
    w, h = rng.randint(2, 5), rng.randint(2, 5)
    count = rng.randint(1, 8)
    items = [(rng.randint(1, w + 1), rng.randint(1, h + 1))
             for _ in range(count)]
    inv = inventory.Inventory(w, h, rotate)
    inv.place_all(items)
    optimum = inventory.optimal_used(w, h, items, rotate)
    # 题面要求物品数 <= 8 时占用格数差 <= 0。
    assert inv.used() <= optimum
    assert_valid_layout(inv)


@pytest.mark.parametrize("seed", range(25))
@pytest.mark.parametrize("rotate", [False, True])
def test_first_fit_vs_bruteforce_optimal_used(seed, rotate):
    """与独立参照暴力对照：首次适配占用 ≤ 最优，且最优解可复现。"""
    rng = random.Random(1000 + seed)
    w, h = rng.randint(2, 4), rng.randint(2, 4)
    items = [(rng.randint(1, 3), rng.randint(1, 3))
             for _ in range(rng.randint(1, 6))]
    inv = inventory.Inventory(w, h, rotate)
    inv.place_all(items)
    reference = _reference_optimum(w, h, items, rotate)
    assert inventory.optimal_used(w, h, items, rotate) == reference
    assert inv.used() <= reference


def test_optimal_rejects_more_than_eight():
    with pytest.raises(ValueError):
        inventory.optimal_used(4, 4, [(1, 1)] * 9)


def test_optimal_exact_known_values():
    # 4x4 中 4 个 2x2 恰好铺满。
    assert inventory.optimal_used(4, 4, [(2, 2)] * 4) == 16
    # 不旋转时，2x3 只能放进 3x2 之一方向。
    assert inventory.optimal_used(3, 2, [(2, 3)]) == 0
    assert inventory.optimal_used(3, 2, [(2, 3)], rotate=True) == 6
    # 同形状的多个物品必须分别计数（不能因去重而少算）。
    assert inventory.optimal_used(5, 5, [(1, 3), (3, 1)], rotate=True) == 6
    assert inventory.optimal_used(4, 4, [(2, 1), (1, 2)], rotate=True) == 4
    # 允许放弃放不下的物品。
    assert inventory.optimal_used(2, 2, [(2, 2), (3, 1)]) == 4
    # 空列表。
    assert inventory.optimal_used(3, 3, []) == 0


def _reference_optimum(w, h, items, rotate):
    """与实现无关的参照暴力：枚举每个物品的每个位置或跳过。"""
    def orientations(item):
        a, b = item
        if rotate and a != b:
            return [(a, b), (b, a)]
        return [(a, b)]

    best = 0

    def rec(index, occupied, used):
        nonlocal best
        best = max(best, used)
        if index == len(items):
            return
        for ow, oh in orientations(items[index]):
            if ow > w or oh > h:
                continue
            for y in range(h - oh + 1):
                for x in range(w - ow + 1):
                    cells = {(x + dx, y + dy)
                             for dy in range(oh) for dx in range(ow)}
                    if cells & occupied:
                        continue
                    rec(index + 1, occupied | cells, used + ow * oh)
        rec(index + 1, occupied, used)  # 跳过该物品

    rec(0, frozenset(), 0)
    return best


@pytest.mark.parametrize("seed", range(60))
def test_optimal_matches_reference_bruteforce(seed):
    rng = random.Random(seed)
    w, h = rng.randint(1, 5), rng.randint(1, 5)
    items = [(rng.randint(1, 4), rng.randint(1, 4))
             for _ in range(rng.randint(0, 6))]
    rotate = rng.random() < 0.5
    assert inventory.optimal_used(w, h, items, rotate) == \
        _reference_optimum(w, h, items, rotate)


@pytest.mark.parametrize("rotate", [False, True])
def test_first_fit_used_equals_optimal_on_fitting_cases(rotate):
    """最优能全放下时，首次适配的占用格数必须等于最优（差为 0）。"""
    cases = [
        (4, 4, [(2, 2)] * 4),
        (4, 4, [(1, 4)] * 4),
        (3, 4, [(3, 2), (3, 2)]),
        (4, 4, [(2, 1), (2, 1), (3, 2)]),
        (4, 4, [(1, 1), (2, 2), (1, 3)]),
    ]
    for w, h, items in cases:
        inv = inventory.Inventory(w, h, rotate)
        inv.place_all(items)
        optimum = inventory.optimal_used(w, h, items, rotate)
        assert inv.used() <= optimum
        if sum(iw * ih for iw, ih in items) == optimum:
            assert inv.used() == optimum
        assert_valid_layout(inv)


# ------------------------------------------------------------------- 性能

def test_performance_10k_placements_under_500ms():
    rng = random.Random(1234)
    size = 16
    items = [(rng.randint(1, 4), rng.randint(1, 4)) for _ in range(10000)]
    inv = inventory.Inventory(size, size, rotate=True)
    start = time.perf_counter()
    count = 0
    for item in items:
        inv.place(item)
        count += 1
        if inv.free() < 1:
            inv.reset()
    elapsed = time.perf_counter() - start
    assert count == 10000
    assert elapsed < 0.5, "1 万次放置耗时 %.3fs" % elapsed
    assert_valid_layout(inv)


def test_performance_worst_case_scans_under_500ms():
    """大量失败放置（几乎满格）也应快速返回 None。"""
    inv = inventory.Inventory(8, 8)
    assert inv.place((8, 8)) == (0, 0)
    start = time.perf_counter()
    for _ in range(10000):
        assert inv.place((2, 2)) is None
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, "1 万次失败放置耗时 %.3fs" % elapsed
