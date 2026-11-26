# inventory

## 题面（可直接粘贴）

背包格子装箱（含最优对照）。约束：放置互不重叠且不越界，旋转可选；首次适配结果与逐项扫描一致；物品数 ≤8 时必须与暴力最优解对照（占用格数差 ≤0）；无空位返回 None 而不抛错，并给出不可放置原因分类；1 万次放置不超过 500 ms。 工作目录为仓库内的 inventory/。 验收：cd inventory && python -m pytest tests -q。 实现只允许使用 Python 标准库。

## 运行方式

```bash
cd inventory && python -m pytest tests -q
```

初始 15 failed（实现前）。仅使用 Python 标准库。

## 字段

- 所属领域：游戏、图形与多媒体
- 子方向：游戏开发
- 任务类型：Bugfix
- 语言/框架：Python 3, pytest
- 环境可复现等级：无外部依赖
