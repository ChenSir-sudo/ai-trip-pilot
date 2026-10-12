"""候选池节点：把槽位变成一批带来源的地点。

位置：规划图的取数节点，在完整性判定说「齐了」之后、求解之前（architecture.md §3）。
    它是 S2 的可演示产出：**给定需求 → 取回候选池，并打印来源**。
可测试性：数据源是**注入**的（`DataAccess`）。测试传一个假实现，因此不需要网络，
    也不需要离线快照——这与模型抽取器用同一个手法（见 architecture.md §8）。
不做的事：不排序、不打分、不筛掉任何地点。筛选是候选**筛选**节点的职责；本节点只
    负责按城市把候选取回来，**并如实带上来源**。

**能力边界必须显式记录，不许吞掉。** 离线侧没有班次、某个类别可能没有映射——这些
都写进 `data_notes` 并由入口打印出来。少取了几类却没人知道，方案里就会莫名少几个
地点，而且**不报错**。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from src.data.base import DataAccess
from src.data.errors import CapabilityUnavailable
from src.data.types import Place
from src.graph.state import TripState

# 候选池按这几类各取一批。
#
# ⚠️ 这是一个**跨数据源的词表**，两份实现都要认它：离线快照里存的就是这些值
# （取自 OSM 的 amenity / tourism 标签值），高德侧则把它们映射成中文类型名
# （映射在 src/data/amap.py，标记为未核实）。
# 之所以限定在这四类，是因为它们**在两边都能落地**——多加一类就可能只有一边认得。
CANDIDATE_CATEGORIES: tuple[str, ...] = ("attraction", "museum", "restaurant", "hotel")


def make_build_candidate_pool(
    data: DataAccess | None,
    *,
    categories: Iterable[str] = CANDIDATE_CATEGORIES,
    per_category: int = 8,
    max_total: int = 30,
) -> Callable[[TripState], dict]:
    """造出 `build_candidate_pool` 节点。

    参数：
      data：数据访问实现。`None` 表示没有注入——**此时节点会明确报错**，而不是
          返回一个空候选池。空候选池会让下游以为「这个城市没有地点」。
      per_category / max_total：配额保护。检索按次计费，个人认证的基础搜索服务
          是每月 5,000 次（见 docs/research/2026-amap-compliance-verify.md）。
    """
    category_list = tuple(categories)

    def build_candidate_pool(state: TripState) -> dict:
        """按目的地取回候选，并把来源与能力边界写进状态。

        契约：
          副作用：向 `data` 发起检索（可能联网、可能计费）。**不写任何存储**——
              真实接口的数据禁止落库（高德协议 3.5 条）。
          幂等性：对离线快照是；对真实接口不是（上游数据会变）。
          失败模式：`data` 为 `None` 时抛 `RuntimeError`；单个类别不可用时**不中断**，
              而是记进 `data_notes` 后继续——**一类取不到不该让整个规划失败**，
              但也不能不留痕迹。
        """
        if data is None:
            raise RuntimeError(
                "候选池节点需要一个数据源。"
                "用 build_graph(data=load_data_access()) 注入，见 src/data/factory.py。"
            )

        slots = state.get("slots") or {}
        city = str(slots.get("destination_city") or "").strip()
        if not city:
            # 图保证到这里必需槽位齐全；走到这里说明有人直接调了这个节点。
            raise ValueError("候选池节点要求 slots.destination_city 非空")

        notes: list[str] = []
        found = []

        # 先解析中心点：真实接口按次数计费，先地理编码再检索是省配额的办法；
        # 解析失败也继续——城市名本身对多数检索接口已经够用，但要说出来。
        if data.resolve_place(name=city, city=city) is None:
            notes.append(f"地名解析没有得到 {city} 的中心点，仍按城市名检索")
        notes.append(f"数据源：{data.describe()}")

        coverage: list[str] = []
        for category in category_list:
            try:
                hits = data.search_place(city=city, category=category, limit=per_category)
            except CapabilityUnavailable as exc:
                coverage.append(f"{category} 不可用")
                notes.append(f"类别「{category}」不可用：{exc}")
                continue
            found.extend(hits)
            coverage.append(f"{category} {len(hits)}")

        # 把各类别的取回条数写出来。**没有它，「候选池里全是餐厅」看不出是词表不匹配
        # 还是数据本来如此**——而这两种原因的处置方式完全不同。
        notes.append("各类别取回：" + " / ".join(coverage))

        # 去重并按 id 定序：同一份输入必须得到同一批候选，否则回归评测不可比。
        # 去重也在这里做一次——reducer 会兜底，但 `max_total` 得按**去重后**的条数算。
        unique: dict[str, Place] = {}
        for place in found:
            unique.setdefault(place.id, place)
        ordered: list[Place] = [unique[key] for key in sorted(unique)]

        if len(ordered) > max_total:
            notes.append(f"候选 {len(ordered)} 条，截到 {max_total} 条")
            ordered = ordered[:max_total]
        if not ordered:
            notes.append(f"{city} 没有取到任何候选地点")

        return {
            "candidates": [place.to_candidate() for place in ordered],
            "data_notes": notes,
        }

    return build_candidate_pool
