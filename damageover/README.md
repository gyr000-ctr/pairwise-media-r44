# damageover

## 题面（可直接粘贴）

持续伤害结算。约束：DOT 按固定 tick 间隔结算且总跳数与时长/间隔一致（含首尾）；每跳按剩余时间比例对齐（末跳不足间隔时按比例），总伤害与 DPS×时长差 ≤1%；多 DOT 叠加按施加序结算且互不影响；刷新不重置已结算跳数（可配置）；10 万次更新不超过 400 ms；非法间隔可区分报错。 工作目录为仓库内的 damageover/。 验收：cd damageover && python -m pytest tests -q。 实现只允许使用 Python 标准库。

## 运行方式

```bash
cd damageover && python -m pytest tests -q
```

初始 15 failed（实现前）。仅使用 Python 标准库。

## 字段

- 所属领域：游戏、图形与多媒体
- 子方向：游戏开发
- 任务类型：Bugfix
- 语言/框架：Python 3, pytest
- 环境可复现等级：无外部依赖
