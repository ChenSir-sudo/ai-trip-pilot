# AI Trip Pilot

**目标形态**：面向多约束行程的出行规划 Agent —— 约束求解 + 检索增强 + 回归评测。

**当前状态**：**第三步**。规划图骨架端到端跑通——共享状态、条件边、澄清的挂起与恢复，**真实的模型抽取**（DeepSeek `deepseek-flash` + 严格 schema）；数据访问层已接上，槽位补齐后会**取回候选池并打印每条来源**。约束求解、评测与界面尚未开始。

> **离线侧红线覆盖说明**：离线快照的营业时间缺失约 98%，所以**断言 A3（停靠点在营业时间内）在离线路径上做不了**，必须记账而不是让它悄悄通过。已知缺口列在 [`data/README.md`](data/README.md)。

> An itinerary planning agent that treats trip planning as a constraint satisfaction problem.
> The graph skeleton runs end to end: shared state, a conditional edge, clarify with
> interrupt/resume, and real model-based slot extraction. The data access layer is wired
> in, so a completed request yields a candidate pool with per-record provenance. The
> constraint solver, evaluation and UI are not started.

---

## 这个项目的核心主张

市面上的 AI 行程工具，通病不是「写得不好听」，而是**方案在物理和时间上根本不成立**——编造不存在的地点、无视营业时间、忽略通勤耗时。ACL 2025 的 [TripTailor](https://aclanthology.org/2025.findings-acl.503/) 基准（50 万+ 真实 POI、近 4 千条真实行程）显示，最新 SOTA 模型生成的行程**达到人类水平的不到 10%**，失败集中在可行性、合理性与个性化。

所以本项目把行程生成**重定义成一个约束满足问题**：

- **可行性由确定性代码保证**，不由模型的提示词祈祷。求解器负责硬约束（时间窗、营业时间、预算、返程可达），语言模型只负责理解需求与解释方案。
- **方案里每个停靠点都必须来自候选池**，按 ID 命中。这条断言把「不要幻觉」从提示词纪律变成架构约束。
- **不可行时必须反问用户，不允许静默放宽约束。**

推理与取舍见 [`docs/adr/`](docs/adr/)。

---

## 现在做到哪一步

| 部分 | 状态 |
|---|---|
| 共享状态 `TripState` + reducer | ✅ 完成 |
| 规划图骨架（条件边 + 澄清循环） | ✅ 完成 |
| 中断与澄清（挂起 / 恢复） | ✅ 完成 |
| 模型接入层（可换供应商，注入式） | ✅ 完成 |
| 槽位抽取（DeepSeek + 严格 schema、失败重试一次） | ✅ 完成 |
| 数据访问层（接口 + 离线快照 + 高德 REST） | ✅ 完成 |
| 候选池节点（槽位齐 → 取回候选并打印来源） | ✅ 完成 |
| 约束求解与红线断言 | ⬜ 未开始 |
| 评测与消融 | ⬜ 未开始 |

图结构与状态通道的**当前事实**由脚本自动导出，不会过期：[`docs/graph.md`](docs/graph.md)。

---

## 怎么跑起来

需要 Python 3.12 与 [uv](https://docs.astral.sh/uv/)：

```bash
uv venv --python 3.12
uv pip install -r requirements-dev.txt

# 配置模型（只有跑 src.main 需要；pytest 完全离线）
cp .env.example .env        # 然后填入 LLM_API_KEY

# 抓一份离线快照（离线实现要用它；不入库，见 data/README.md）
python -m scripts.fetch_offline_data --limit 400

# 跑一次图（必须在仓库根目录，用 -m 形式）
python -m src.main

# 跑测试（不需要 key，不联网）
python -m pytest -q

# 重新导出图文档（改过图或状态之后）
python -m scripts.export_graph
```

两条硬约束，是 `src.` 前缀包布局的固有代价，不是配置问题：

```bash
python src/main.py      # ✖ ModuleNotFoundError: No module named 'src'
python -m src.main      # ✔
```

> 中国大陆网络环境下，`uv` **不读** pip 的镜像配置。安装前设一次：
> `export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`

---

## 文档地图

| 文件 | 回答什么问题 |
|---|---|
| [`CONTEXT.md`](CONTEXT.md) | **词汇表**：术语的唯一定义与禁用同义词 |
| [`docs/prd.md`](docs/prd.md) | 产品决策：做什么、不做什么、评测方案、路线图 |
| [`docs/architecture.md`](docs/architecture.md) | 实现：分层、图的节点、求解建模、数据层、检索 |
| [`docs/adr/`](docs/adr/) | 为什么偏偏这么做（不可逆决策） |
| [`docs/graph.md`](docs/graph.md) | 图的当前事实（**自动生成，不要手改**） |
| [`docs/code-comments.md`](docs/code-comments.md) | 代码注释规范 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 提交信息规范（中英双语）与提交钩子 |
| [`docs/research/`](docs/research/) | 调研报告：工程实践、数据源可得性、合规核实 |

**文档边界是刻意画开的**：词汇只放 `CONTEXT.md`，产品决策只放 `prd.md`，实现细节只放 `architecture.md`，代码注释不复述它们。任何一处改动都只有唯一落点。

---

## 技术栈

Python 3.12 ｜ [LangGraph](https://langchain-ai.github.io/langgraph/) ｜ pytest

约束求解、数据访问、检索与可观测性的选型见 [`docs/architecture.md`](docs/architecture.md) 与 [`docs/adr/`](docs/adr/)。

---

## 关于这个项目

它是一个**学习用项目**：每个技术点都必须落在核心路径上、并且能被验证，而不是为了出现在技术栈列表里。因此文档里记录了取舍与代价，也记录了**已知的不足**。

数据的合规边界是认真的：地图服务条款禁止平台外存储与缓存，本项目的开发与评测一律走离线数据集，真实接口只用于演示。详见 [`docs/research/2026-amap-compliance-verify.md`](docs/research/2026-amap-compliance-verify.md)。

**本仓库暂未添加开源许可证**，即在默认法律含义下保留所有权利。
