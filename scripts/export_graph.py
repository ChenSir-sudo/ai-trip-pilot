"""把当前规划图的事实导出成 docs/graph.md。

位置：开发工具，不在运行时路径上。输入是 `src/graph` 构建出的图。
可测试性：不联网、不调模型、不需要密钥，可以在 CI 里跑并断言输出内容。
不做的事：**不手写任何图或表**——所有内容都从代码推导。一旦这个文件里出现
    硬编码的节点名或字段名，这份文档就开始过期了，而它存在的全部意义就是不过期。

用法：
    python -m scripts.export_graph              # 写入 docs/graph.md
    python -m scripts.export_graph <路径>        # 写入指定位置
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from src.graph.builder import build_graph

# 仓库根目录：本文件在 <root>/scripts/ 下。
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "docs" / "graph.md"


def _is_internal_channel(name: str) -> bool:
    """框架自己用的通道（`__start__`、`branch:*` 等），不是业务状态字段。"""
    return name.startswith("__") or name.startswith("branch:")


def _describe_channel(channel) -> tuple[str, str]:
    """把框架的通道对象翻译成「合并语义 + 说明」。

    契约：
      副作用：无。
      幂等性：是。
      失败模式：不抛异常。遇到未知通道类型时返回「未知」并带上类名，
          让它在文档里显形——静默当成「覆盖」会把错误藏起来。
    """
    kind = type(channel).__name__
    if kind == "LastValue":
        return "覆盖", "后写的整体替换先写的"
    if kind == "BinaryOperatorAggregate":
        # 存合并函数的属性叫 operator（不是 reducer）。
        operator = getattr(channel, "operator", None)
        return "合并", getattr(operator, "__name__", repr(operator))
    return "未知", kind


def collect_state_rows(graph) -> list[dict]:
    """导出状态通道清单，按字段名排序以保证输出稳定。

    返回的每一项含 `field` / `semantics` / `detail` 三个键。

    为什么没有「写入者 / 读取者」两列：那需要静态分析或运行期埋点，框架不提供。
    靠人读代码填出来的列会随代码漂移，正是本脚本要消灭的东西——宁可少一列，
    也不要一列看起来权威但没人维护的数据。
    """
    rows = []
    for name, channel in graph.channels.items():
        if _is_internal_channel(name):
            continue
        semantics, detail = _describe_channel(channel)
        rows.append({"field": name, "semantics": semantics, "detail": detail})
    return sorted(rows, key=lambda row: row["field"])


def collect_node_rows(graph) -> list[dict]:
    """导出节点清单及其文档字符串首行。

    文档字符串是代码里已经存在的说明，这里只是搬运——不新增描述，
    避免同一件事有两处说法。
    """
    rows = []
    for name in graph.get_graph().nodes:
        if name.startswith("__"):
            continue
        bound = getattr(graph.nodes.get(name), "bound", None)
        func = getattr(bound, "func", None)
        summary = ((getattr(func, "__doc__", None) or "").strip().split("\n") or [""])[0]
        rows.append({"node": name, "summary": summary or "（无文档字符串）"})
    return sorted(rows, key=lambda row: row["node"])


def _git(*args: str) -> str:
    """跑一条 git 命令，失败时返回空串。

    失败是允许的：脚本可能在没有 git 的环境里被调用，文档的「来源」一节
    会因此显示为未知，而不是让整个导出失败。
    """
    try:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _has_code_changes(porcelain: str, *, exclude_rel: str | None) -> bool:
    """从 `git status --porcelain` 的输出判断「除生成物以外」是否有改动。

    契约：
      副作用：无。纯函数，接受字符串而不是自己去跑 git —— 这样它可以被单测。
      幂等性：是。
      失败模式：不抛异常。无法解析的行一律当成「有改动」，宁可多报也不要漏报。
    """
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().strip('"')
        if exclude_rel and path == exclude_rel:
            continue
        return True
    return False


def render(graph, *, generated_at: str, commit: str, dirty: bool) -> str:
    """渲染整份文档。

    契约：
      副作用：无（纯函数，不写文件）。
      幂等性：是——除 `generated_at` 外，相同代码产生相同输出。
      失败模式：不抛异常。schema 缺失时跳过该节。
    """
    lines: list[str] = []

    lines += [
        "# 规划图（自动生成）",
        "",
        "> ⚠️ **本文件由脚本生成，不要手改。** 改图或改状态之后重新运行：",
        ">",
        "> ```bash",
        "> python -m scripts.export_graph",
        "> ```",
        ">",
        f"> - 生成时间：{generated_at}",
        f"> - 生成自提交：`{commit or '未知'}`"
        + (
            "（生成时代码有未提交改动，本文件可能与你看到的代码不一致）"
            if dirty
            else "（生成时代码已全部提交）"
        ),
        "> - 内容全部从代码推导；本文件里没有任何手写的节点名或字段名",
        "",
        "## 一、拓扑",
        "",
        "由框架从代码现算，因此不会过期。内部通道（`__start__`、`branch:*`）已过滤。",
        "",
        "```mermaid",
        graph.get_graph().draw_mermaid().strip(),
        "```",
        "",
        "## 二、状态通道",
        "",
        "语义由框架的通道类型决定，不是约定：挂了 reducer 的字段才会「合并」，",
        "其余字段一律整体覆盖。",
        "",
        "| 字段 | 合并语义 | 说明 |",
        "|---|---|---|",
    ]

    for row in collect_state_rows(graph):
        lines.append(f"| `{row['field']}` | **{row['semantics']}** | {row['detail']} |")

    lines += [
        "",
        "> **本表刻意没有「写入者 / 读取者」两列。** 它们需要对节点做静态分析或运行期",
        "> 埋点，框架不提供。靠人读代码填的列会随代码漂移——宁可少一列，也不要一列",
        "> 看起来权威却没人维护的数据。将来要补，正确做法是在节点上加埋点，而不是手填。",
        "",
        "## 三、节点",
        "",
        "| 节点 | 文档字符串首行 |",
        "|---|---|",
    ]

    for row in collect_node_rows(graph):
        lines.append(f"| `{row['node']}` | {row['summary']} |")

    lines += ["", "## 四、状态形状（输入 JSON Schema）", "", "<details>", "<summary>展开</summary>", "", "```json"]

    try:
        import json

        lines.append(json.dumps(graph.get_input_jsonschema(), ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001 —— 导出工具不该因为缺 schema 就整体失败
        lines.append(f"（无法导出：{exc}）")

    lines += ["```", "", "</details>", ""]

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """入口：生成文档并写入磁盘。

    契约：
      副作用：写一个文件。
      失败模式：目标目录不可写时抛 OSError —— 这里不吞异常，
          因为「导出悄悄失败」比「导出报错」危险得多。
    """
    args = list(sys.argv[1:] if argv is None else argv)
    # resolve()：让相对路径也能正确判断是否落在仓库内（决定是否把自身排除在改动之外）
    output = Path(args[0]).resolve() if args else DEFAULT_OUTPUT

    # 判断「代码」有没有未提交改动时，必须排除生成物自身：否则每次重新生成都会
    # 把它自己算成改动，那句提示永远显示「有未提交改动」，也就不再传递任何信息。
    relative = str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else None

    content = render(
        build_graph(),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        commit=_git("rev-parse", "--short", "HEAD"),
        dirty=_has_code_changes(_git("status", "--porcelain"), exclude_rel=relative),
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")

    print(f"已写入 {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
