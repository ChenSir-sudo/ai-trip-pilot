"""完整性判定的规则测试。

规则与图分开，所以这里不构建图、不依赖 LangGraph——直接调函数。
规则的正确性不该被图的实现细节掩盖。
"""

from __future__ import annotations

from src.graph.completeness import find_missing_slots


def test_empty_slots_report_everything_missing():
    """什么都没给时，必需槽位与二选一组全部报缺。"""
    assert find_missing_slots({}) == ["出发城市", "目的城市", "出发日期 或 天数"]


def test_none_slots_report_everything_missing():
    """slots 传 None 不该抛异常——节点可能读到一个还没被写过的字段。"""
    assert find_missing_slots(None) == ["出发城市", "目的城市", "出发日期 或 天数"]


def test_either_group_is_satisfied_by_days_alone():
    """知道「待几天」就够排期，不必再问出发日期。"""
    slots = {"origin_city": "杭州", "destination_city": "上海", "days": 5}

    assert find_missing_slots(slots) == []


def test_either_group_is_satisfied_by_date_alone():
    """反过来，只知道出发日期也够。"""
    slots = {"origin_city": "杭州", "destination_city": "上海", "depart_date": "2026-07-01"}

    assert find_missing_slots(slots) == []


def test_whitespace_only_string_counts_as_missing():
    """空白字符串与「没给」在规划上等价。

    否则模型返回一个 {"origin_city": "   "} 就能骗过判定，
    然后带着缺槽位往下跑——这类错误不报错，只会静默跑偏。
    """
    slots = {"origin_city": "   ", "destination_city": "上海", "days": 5}

    assert find_missing_slots(slots) == ["出发城市"]


def test_none_value_counts_as_missing():
    slots = {"origin_city": None, "destination_city": "上海", "days": 5}

    assert find_missing_slots(slots) == ["出发城市"]


def test_missing_order_is_stable():
    """顺序稳定，澄清问句才不会每次都不一样。"""
    assert find_missing_slots({"days": 3}) == ["出发城市", "目的城市"]
