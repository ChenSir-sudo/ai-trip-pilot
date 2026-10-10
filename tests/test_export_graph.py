"""导出脚本的测试。

这个脚本的产物是给人看的文档，所以它坏掉时不会有人立刻发现——
这几条测试就是那个「立刻发现」。
"""

from __future__ import annotations

from scripts.export_graph import (
    _has_code_changes,
    collect_node_rows,
    collect_state_rows,
    render,
)
from src.graph.builder import build_graph

GENERATED_AT = "2026-01-01 00:00:00"


def test_state_rows_mark_candidates_as_merge_and_others_as_overwrite():
    """状态语义：candidates 是合并型，其余是覆盖型。

    这条测试守着导出结果里最容易出错的一格——合并语义是接口契约，
    导错了会让人以为某个字段可以随便覆盖。
    """
    rows = {row["field"]: row for row in collect_state_rows(build_graph())}

    assert rows["candidates"]["semantics"] == "合并"
    assert rows["candidates"]["detail"] == "merge_candidates"
    assert rows["slots"]["semantics"] == "覆盖"
    assert rows["missing_slots"]["semantics"] == "覆盖"


def test_internal_channels_are_filtered_out():
    """内部通道不得出现在状态表里——它们不是业务字段。"""
    names = {row["field"] for row in collect_state_rows(build_graph())}

    assert names, "状态表不应为空"
    assert not any(n.startswith("__") or n.startswith("branch:") for n in names)


def test_node_rows_carry_docstring_summary():
    """节点清单搬运代码里已有的说明，不新增描述。"""
    rows = {row["node"]: row for row in collect_node_rows(build_graph())}

    assert rows["extract_slots"]["summary"] == "把出行需求原文抽成结构化槽位。"


def test_render_contains_topology_provenance_and_staleness_warning():
    """渲染结果必须自带「不要手改」与来源信息，否则它会悄悄过期。"""
    markdown = render(
        build_graph(), generated_at=GENERATED_AT, commit="deadbee", dirty=True
    )

    assert "```mermaid" in markdown
    assert "extract_slots" in markdown
    assert "不要手改" in markdown
    assert "deadbee" in markdown
    assert "未提交" in markdown
    assert GENERATED_AT in markdown


def test_render_is_deterministic_except_timestamp():
    """除时间戳外，相同代码必须产生相同输出——否则 diff 里全是噪音。"""
    first = render(build_graph(), generated_at=GENERATED_AT, commit="c", dirty=False)
    second = render(build_graph(), generated_at=GENERATED_AT, commit="c", dirty=False)

    assert first == second


def test_dirty_check_ignores_the_generated_file_itself():
    """生成物自己不算「代码改动」，否则那句提示永远为真、永远没有信息量。"""
    porcelain = " M docs/graph.md\n"

    assert _has_code_changes(porcelain, exclude_rel="docs/graph.md") is False
    assert _has_code_changes(porcelain, exclude_rel=None) is True


def test_dirty_check_still_detects_real_code_changes():
    """排除生成物不等于什么都不报——真正的代码改动必须照报。"""
    porcelain = "?? src/graph/new_node.py\n M docs/graph.md\n"

    assert _has_code_changes(porcelain, exclude_rel="docs/graph.md") is True


def test_dirty_check_treats_empty_output_as_clean():
    """干净的工作区不能被误报成有改动。"""
    assert _has_code_changes("", exclude_rel="docs/graph.md") is False
