# aggro

## 题面（可直接粘贴）

仇恨表与目标选择。约束：仇恨按距离衰减的增量累加且溢出钳制；目标选择取最大仇恨（平局按加入序）；仇恨随时间为指数衰减且与解析式 ≤1e-9；嘲讽强制切换并保持 N 秒；10 万次更新不超过 300 ms；非法增量可区分报错。 工作目录为仓库内的 aggro/。 验收：cd aggro && python -m pytest tests -q。 实现只允许使用 Python 标准库。

## 运行方式

```bash
cd aggro && python -m pytest tests -q
```

初始 15 failed（实现前）。仅使用 Python 标准库。

## 字段

- 所属领域：游戏、图形与多媒体
- 子方向：游戏开发
- 任务类型：Bugfix
- 语言/框架：Python 3, pytest
- 环境可复现等级：无外部依赖
