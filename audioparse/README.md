# audioparse

## 题面（可直接粘贴）

PCM 容器头解析（WAV/AIFF/RF64）。约束：三格式都解析出声道/采样率/位深且与构造值一致；24 位打包/解包往返无损（≤1e-12）；未知块与 fact/LIST 块跳过而不失败；三类损坏（截断/魔数/长度不符）给出可区分错误并报告偏移；偶字节对齐校验；10 万次解析不超过 600 ms。 工作目录为仓库内的 audioparse/。 验收：cd audioparse && python -m pytest tests -q。 实现只允许使用 Python 标准库。

## 运行方式

```bash
cd audioparse && python -m pytest tests -q
```

初始 15 failed（实现前）。仅使用 Python 标准库。

## 字段

- 所属领域：游戏、图形与多媒体
- 子方向：音视频处理
- 任务类型：Bugfix
- 语言/框架：Python 3, pytest
- 环境可复现等级：无外部依赖
