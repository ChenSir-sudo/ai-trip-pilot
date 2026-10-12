"""测试用的假数据源。

**为什么是普通模块而不是 conftest 里的 fixture**：根目录的 conftest.py 已经写明
「不做任何 fixture——一旦放共享 fixture，测试就开始依赖隐藏的上下文」。这里遵守
那条立场：用它的测试**显式 import**，读者一眼能看出这个测试依赖一个假数据源。

**为什么集中放一处**：`test_graph` 与 `test_candidate_pool` 都要用它。复制两份必然
分叉，而分叉的假实现会让两个测试文件的结论互相矛盾。
"""

from __future__ import annotations

_UNSET = object()

from src.data.errors import CapabilityUnavailable
from src.data.types import Place, Provenance


def make_place(
    place_id: str = "fake:1",
    *,
    name: str = "测试地点",
    category: str | None = "attraction",
    city: str | None = "测试城",
    lat: float = 30.0,
    lon: float = 120.0,
    opening_hours: str | None = None,
) -> Place:
    """造一个假地点。**这是测试数据，不是产品数据。**"""
    return Place(
        id=place_id,
        name=name,
        lat=lat,
        lon=lon,
        category=category,
        city=city,
        adcode=None,
        opening_hours=opening_hours,
        provenance=Provenance(
            source="fake", as_of="2026-10-11", is_sample=True, license="test-only"
        ),
    )


class FakeDataAccess:
    """假的 `DataAccess`：返回预置地点，不发任何请求。

    它让图的测试不必联网、不必有快照、不必有 key——**这正是依赖注入要买到的东西**
    （见 architecture.md §8）。
    """

    def __init__(
        self,
        places: list[Place] | None = None,
        *,
        resolved: Place | None = _UNSET,  # type: ignore[assignment]
        unavailable: tuple[str, ...] = (),
    ) -> None:
        self.places = list(places if places is not None else [make_place()])
        # 用哨兵而不是 None 做默认值：**`resolved=None` 是有意义的输入**
        # （表示「解析不到中心点」），不能和「没传这个参数」混为一谈。
        self.resolved = (
            (self.places[0] if self.places else None) if resolved is _UNSET else resolved
        )
        self.unavailable = set(unavailable)
        self.searches: list[tuple[str, str | None]] = []

    def describe(self) -> str:
        return "假数据源（测试用，非真实数据）"

    def search_place(self, *, city, keywords=None, category=None, limit=50):
        if not keywords and not category:
            raise ValueError("检索要求 keywords 与 category 至少给一个（契约见 base.py）")
        self.searches.append((city, category))
        if category in self.unavailable:
            raise CapabilityUnavailable(f"{category} 在这个假数据源上不可用")
        hits = [p for p in self.places if category is None or p.category == category]
        return hits[:limit]

    def resolve_place(self, *, name, city=None):
        return self.resolved

    def route(self, *, origin, destination, mode):
        raise CapabilityUnavailable("假数据源不做路线")

    def weather(self, *, adcode, date):
        raise CapabilityUnavailable("假数据源不做天气")

    def train_schedule(self, *, from_city, to_city, date):
        raise CapabilityUnavailable("假数据源不做班次")

    def lookup_area(self, *, adcode):
        return None
