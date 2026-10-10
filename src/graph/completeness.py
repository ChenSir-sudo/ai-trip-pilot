"""完整性判定：哪些槽位是必需的，以及当前缺哪些。

位置：决策层。被规划图的 `check_completeness` 节点调用（见 docs/architecture.md §3）。
可测试性：纯函数，不 import 图框架、不联网、不调模型——规则可以脱离图被单测。
不做的事：不解析出行需求（那是 `extract_slots` 的职责）；不判断软偏好；
    不决定该怎么问用户（那是 `clarify` 的职责）。
"""

from __future__ import annotations

# 槽位键用英文（代码里的标识符），标签用中文（问给用户的原话）。
# 两者分开放，是为了让状态里的数据与呈现给用户的文案各归其位。
_SLOT_LABELS: dict[str, str] = {
    "origin_city": "出发城市",
    "destination_city": "目的城市",
    "depart_date": "出发日期",
    "days": "天数",
}

# 必需槽位：缺任意一个都无法开始规划。
REQUIRED_SLOTS: tuple[str, ...] = ("origin_city", "destination_city")

# 二选一槽位：组内知道任一即可。
# 「出发日期」与「天数」是同一件事（什么时候去、待多久）的两种说法，
# 用户给哪个都够排期；但两个都没有就必须问。
EITHER_SLOTS: tuple[tuple[str, ...], ...] = (("depart_date", "days"),)


def _present(slots: dict, key: str) -> bool:
    """槽位存在且不是空值才算「给了」。

    「没给」与「给了空字符串」在规划上等价，都算缺失——否则模型返回一个
    `{"origin_city": ""}` 就能骗过完整性判定，然后带着缺槽位往下跑。
    """
    value = (slots or {}).get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def find_missing_slots(slots: dict) -> list[str]:
    """返回缺失项的**中文标签**清单，供澄清使用。

    契约：
      副作用：无。纯函数。
      幂等性：是。
      失败模式：不抛异常。`slots` 为空或缺键都返回「全缺」。

    返回标签而不是键，是因为这个清单的消费者是 `clarify`——它要问用户的原话
    就是这些词。二选一组给出「出发日期 或 天数」这样的表述，因为那正是该问的话。
    """
    missing: list[str] = []

    for key in REQUIRED_SLOTS:
        if not _present(slots, key):
            missing.append(_SLOT_LABELS[key])

    for group in EITHER_SLOTS:
        if not any(_present(slots, key) for key in group):
            missing.append(" 或 ".join(_SLOT_LABELS[key] for key in group))

    return missing
