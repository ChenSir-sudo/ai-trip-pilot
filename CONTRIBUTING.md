# 贡献规范

本项目目前只有一位贡献者，但规范仍然要写成文字——因为**半年后的你会忘记当初的约定**，而 AI 协作工具每次都需要重新被告知规则。

## 一、提交信息规范（Conventional Commits · 英文为主）

### 格式

```
<type>(<scope>): <English description>     ← 第 1 行：英文
                                            ← 空行
<中文对照>                                  ← 第 3 行：中文
                                            ← 空行
[English body]                              ← 可选正文：英文在前
                                            ← 空行
[中文正文]                                  ← 可选正文：中文在后
                                            ← 空行
[Footer: Refs / BREAKING CHANGE]            ← 可选
```

### 逐行规则

| 行 | 规则 |
|---|---|
| **第 1 行** | `<type>(<scope>): <English description>`。**全英文、纯 ASCII**，祈使语气，首字母小写（专有名词除外），不超过 72 字符，**结尾不加句号** |
| **第 2 行** | 空行（必需） |
| **第 3 行** | **中文对照**，与首行语义一致，**不带 `type(scope):` 前缀**。它给人读，不参与工具解析 |
| **之后** | 空行 + 可选正文。正文写「为什么」而不是「做了什么」。**英文段在前、中文段在后**，两段之间空一行 |
| **Footer** | 保持英文，放在最后：`Refs: #12`、`BREAKING CHANGE: ...`、`Co-authored-by: ...` |

### 为什么英文在前

`git log --oneline`、GitHub 的提交列表以及绝大多数工具**只显示第一行**。把它写成英文，仓库对任何语言的读者都可读；中文对照紧随其后，保证语义精确、不被翻译损失。

这与「文档正文用中文」并不矛盾：**文档是给人从头读的，提交首行是给工具和所有人扫的。**

### type 取值

`feat` 新功能 ｜ `fix` 修缺陷 ｜ `docs` 文档 ｜ `refactor` 重构（不改行为）｜ `test` 测试 ｜ `perf` 性能 ｜ `build` 构建与依赖 ｜ `ci` 持续集成 ｜ `chore` 杂项 ｜ `revert` 回滚

### scope 取值

与本项目的结构对应：

`context`（词汇表）｜ `prd` ｜ `arch` ｜ `adr` ｜ `research` ｜ `llm`（模型接入）｜ `shell`（编排外壳）｜ `graph`（规划图）｜ `solver`（约束求解）｜ `verify`（红线断言）｜ `data`（数据访问层）｜ `memory` ｜ `eval` ｜ `web` ｜ `cli`（命令行入口）｜ `deps` ｜ `repo`

改动跨多个模块时可省略 scope，例如 `docs: ...`。

### 示例

**合格**

```
docs(prd): add product requirements and architecture design

新增产品文档与架构设计

Record the three mainlines, eight product redlines and the six-week roadmap,
together with four ADRs.

明确三条主线、8 条产品红线与阶段路线图，并同步落盘 4 条 ADR。
Refs: CONTEXT.md
```

```
feat(solver): return minimal conflict sets when infeasible

求解不可行时返回最小冲突约束集

Clarifying questions need to know which constraints collide, not merely that
no solution exists. This is the only entry point that turns a solver failure
into a product experience.

澄清问题需要知道「是哪几条约束打架」，而不是只得到「无解」。
这是把求解失败转成产品体验的唯一入口。
Refs: ADR-0001
```

**不合格**

```
update files                    ← 无 type、无 scope、无信息量
fix: fix the thing.             ← 描述空泛、有句号
fix: 修改了一些东西              ← 首行不是英文（中文对照必须放第 3 行）
feat: add stuff and refactor    ← 一次提交做了两件事，且缺中文对照
```

## 二、提交粒度

- **一次提交只做一件事**。修缺陷与重构不要混在一起。
- 文档改动与代码改动**默认分开提交**；除非它们是同一个决策的两面（此时在正文里说明关联）。
- 提交必须能独立通过检查：不要提交「半成品 + 下一个提交才修好」的状态。

## 三、禁止入库的内容

- 任何密钥、Token、`.env` 文件（`.gitignore` 已排除，但提交前仍要肉眼确认一次）。
- 离线数据集本体（体积大，且许可多为「可下载但不可再分发」）。
- **评测隐藏挑战集**（`eval/cases/hidden/`）——它一旦进仓库就不再是隐藏集，防过拟合的作用随之失效。

## 四、文档纪律

- **一切命名以 [CONTEXT.md](./CONTEXT.md) 为准**。新概念先落词汇表，再进代码与文档。
- 产品决策写进 [docs/prd.md](./docs/prd.md)，实现细节写进 [docs/architecture.md](./docs/architecture.md)，**词汇表只放词汇**。三者的边界不要互相污染。
- 任何**不可逆**且**反直觉**的决策，补一条 [ADR](./docs/adr/)。判断标准见 [ADR 格式说明](https://github.com/joelparkerhenderson/architecture-decision-record)：难以回退、外人会问「为什么这么做」、且当时存在真实的替代方案——三条同时满足才写。
- 文档中引用的任何数字必须带出处（指向 [docs/research/](./docs/research/) 中的报告）。**没测过的写「未测」，不写估计值。**
- **代码注释遵循 [docs/code-comments.md](./docs/code-comments.md)**：注释是第五层文档，不复述上层内容，只写「为什么」与契约。术语必须用 CONTEXT.md 的词，`_Avoid_` 列出的同义词出现在注释里即为违规。

## 五、提交钩子（第一节规范的自动校验）

规范只写在文档里容易被忘掉，因此本仓库带一个钩子：[`.githooks/commit-msg`](./.githooks/commit-msg)。它在每次 `git commit` 时校验提交信息，不合规直接拒绝。

### 启用

`core.hooksPath` 是**本地配置，不随 clone 传播**，所以每个新克隆都要执行一次：

```bash
git config core.hooksPath .githooks
```

### 校验什么

| 规则 | 不通过时 |
|---|---|
| 首行匹配 `<type>(<scope>): <描述>`，type 在取值表内 | 拒绝 |
| 首行结尾不得有 `。` 或 `.` | 拒绝 |
| 首行必须含中文（不能是纯英文） | 拒绝 |
| 第 2 行必须是空行 | 拒绝 |
| 第 3 行必须非空（英文说明） | 拒绝 |

`Merge` / `Revert` / `fixup!` / `squash!` 开头的消息放行；空消息交给 git 自己拒绝。

### 刻意不校验什么

- **首行长度**：中英文混排的「字符数」含义模糊，只作为文档中的建议（50 字符）。
- **scope 是否在清单内**：scope 是判断问题不是格式问题，强行白名单会在新增模块时产生无谓的误拒。
- **第 3 行是否为英文**：无法可靠判定，只校验非空。

这三项靠自觉。**钩子的价值在于拦住明显的遗忘，不在于替人做判断**——把误拒率压到零，它才会一直被启用。

### 边界

- `git commit --no-verify` 可以绕过。这是护栏，不是安全边界。
- 钩子是**本地**强制。若将来需要不可绕过的校验（例如多人协作后），在 CI 中加一步校验提交信息即可，两者互补。
