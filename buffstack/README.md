# buffstack

## 题面（可直接粘贴）

Buff 叠加与刷新。约束：同类 buff 按刷新（重置时长）或叠加（层数上限）两种策略；剩余时间按列表更新且到期移除（顺序稳定）；层数上限钳制且溢出忽略；同帧多次施加顺序无关（可交换性校验）；10 万次更新不超过 300 ms；非法层数可区分报错。 工作目录为仓库内的 buffstack/。 验收：cd buffstack && python -m pytest tests -q。 实现只允许使用 Python 标准库。

## 运行方式

```bash
cd buffstack && python -m pytest tests -q
```

初始 15 failed（实现前）。仅使用 Python 标准库。

## 字段

- 所属领域：游戏、图形与多媒体
- 子方向：游戏开发
- 任务类型：Bugfix
- 语言/框架：Python 3, pytest
- 环境可复现等级：无外部依赖
