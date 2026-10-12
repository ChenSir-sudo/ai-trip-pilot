"""高德 REST 实现的测试。

**全部离线**：取数函数是注入的，测试自己给响应。这样上游的字段名与类型陷阱
（「存在时字符串、不存在时数组」）能被钉住，而不需要一个真实 Key。
不做的事：不发真实请求；上游契约的核实属于调研文档，不属于测试。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.data.amap import AmapRepository
from src.data.errors import CapabilityUnavailable, MissingCredential, UpstreamError
from src.data.types import LatLon, RouteBasis, RouteMode

OK = {"status": "1", "info": "OK", "infocode": "10000"}


class FakeFetch:
    """记录调用并返回预置响应的取数函数。"""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        self.calls.append((url, dict(params)))
        for key, payload in self.routes.items():
            if key in url:
                return payload(len(self.calls), params) if callable(payload) else payload
        raise AssertionError(f"测试没有为 {url} 准备响应")

    @property
    def paths(self) -> list[str]:
        return [u.split("/v3/", 1)[-1].split("/v4/", 1)[-1] for u, _ in self.calls]


def repo(routes: dict[str, Any]) -> tuple[AmapRepository, FakeFetch]:
    fetch = FakeFetch(routes)
    return AmapRepository("fake-key", fetch=fetch), fetch


# ── 凭据与错误映射：排查方向必须是错的才对 ───────────────────────────


def test_empty_key_fails_at_construction_not_at_first_request():
    """缺凭据是配置问题，要在构造时就说，而不是等上游拒绝。"""
    with pytest.raises(MissingCredential, match="AMAP_API_KEY"):
        AmapRepository("   ")


def test_invalid_user_key_is_mapped_to_missing_credential():
    """实测拿到的唯一错误码：无 key 请求返回 10001 INVALID_USER_KEY。

    映射成「缺凭据」而不是「上游故障」——因为要做的事完全不同：
    去填 .env，不是去查高德的状态页。
    """
    client, _ = repo(
        {"place/text": {"status": "0", "info": "INVALID_USER_KEY", "infocode": "10001"}}
    )

    with pytest.raises(MissingCredential, match="10001"):
        client.search_place(city="杭州", keywords="博物馆")


def test_other_upstream_errors_keep_the_code_and_the_message():
    """只回灌「失败了」没有用——高德的错误码是能查的，丢掉它等于丢掉排查起点。"""
    client, _ = repo(
        {"place/text": {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT", "infocode": "10003"}}
    )

    with pytest.raises(UpstreamError) as excinfo:
        client.search_place(city="杭州", keywords="博物馆")
    assert "10003" in str(excinfo.value)
    assert "DAILY_QUERY_OVER_LIMIT" in str(excinfo.value)


def test_unverified_endpoints_are_refused_by_a_guard():
    """不在 _VERIFIED 里的端点不允许被调用。

    这是防止「按记忆猜参数」的机械约束：猜出来的参数会让代码看起来对、上游其实不认。
    """
    client, _ = repo({})
    with pytest.raises(ValueError, match="未核到字段级"):
        client._call("v3/config/district", {})


# ── 检索 ─────────────────────────────────────────────────────────────


def _poi(**over: Any) -> dict[str, Any]:
    base = {
        "id": "B0FFFAB6J2",
        "name": "浙江省博物馆",
        "type": "科教文化服务;博物馆;博物馆",
        "location": "120.1470,30.2530",
        "adcode": "330100",
        "cityname": "杭州市",
        "pname": "浙江省",
    }
    return {**base, **over}


def test_search_sends_the_params_that_make_city_fields_available():
    """`extensions=all` 是决定性的：`adcode` / `cityname` 只有它才返回。"""
    client, fetch = repo({"place/text": {**OK, "pois": [_poi()]}})

    client.search_place(city="杭州", keywords="博物馆")

    _, params = fetch.calls[0]
    assert params["extensions"] == "all", "没有它就拿不到 adcode / cityname"
    assert params["citylimit"] == "true"
    assert params["city"] == "杭州"
    assert params["keywords"] == "博物馆"


def test_search_parses_a_poi_into_a_place_with_its_city():
    client, _ = repo({"place/text": {**OK, "pois": [_poi()]}})

    place = client.search_place(city="杭州", keywords="博物馆")[0]

    assert place.id == "amap:B0FFFAB6J2", "id 要带来源前缀，供 A1 与来源溯源使用"
    assert place.adcode == "330100"
    assert place.city == "杭州市"
    assert place.provenance.source == "amap"
    assert place.provenance.is_sample is False, "真实接口的数据不是示例数据"


def test_location_is_lon_lat_not_lat_lon():
    """**顺序写反不会报错，只会让所有距离都离谱。**

    高德返回 `"经度,纬度"`，与常见的 lat,lon 相反。这一条把它钉死。
    """
    client, _ = repo({"place/text": {**OK, "pois": [_poi(location="120.1470,30.2530")]}})

    place = client.search_place(city="杭州", keywords="博物馆")[0]

    assert place.lat == pytest.approx(30.2530)
    assert place.lon == pytest.approx(120.1470)


def test_search_pages_until_the_limit_then_stops():
    def page(n: int, _params: dict[str, str]) -> dict[str, Any]:
        return {**OK, "pois": [_poi(id=f"P{n}-{i}") for i in range(25)]}

    client, fetch = repo({"place/text": page})

    found = client.search_place(city="杭州", keywords="博物馆", limit=30)

    assert len(found) == 30
    assert len(fetch.calls) == 2, "取够 30 条就该停，不要多花配额"


def test_search_stops_on_a_short_page():
    def page(n: int, _params: dict[str, str]) -> dict[str, Any]:
        if n == 1:
            return {**OK, "pois": [_poi(id=f"P{i}") for i in range(25)]}
        return {**OK, "pois": [_poi(id="last")]}

    client, fetch = repo({"place/text": page})

    found = client.search_place(city="杭州", keywords="博物馆", limit=100)

    assert len(found) == 26
    assert len(fetch.calls) == 2, "短页表示没有更多，不要再翻"


def test_search_rejects_calling_without_keywords_or_category():
    client, _ = repo({})
    with pytest.raises(ValueError, match="至少给一个"):
        client.search_place(city="杭州")


def test_search_returns_empty_list_when_upstream_has_nothing():
    """「查到了但没有」是正常结果，不是错误。"""
    client, _ = repo({"place/text": {**OK, "pois": []}})

    assert client.search_place(city="杭州", keywords="不存在的东西") == []


def test_a_poi_without_a_coordinate_is_an_error_not_a_dropped_row():
    """静默跳过会让候选池少一个地点却不留痕迹。"""
    client, _ = repo({"place/text": {**OK, "pois": [_poi(location=[])]}})

    with pytest.raises(UpstreamError, match="坐标"):
        client.search_place(city="杭州", keywords="博物馆")


def test_a_poi_without_an_id_is_an_error():
    """没有 id 就没法按 ID 命中，A1 会退化成字符串比对。"""
    client, _ = repo({"place/text": {**OK, "pois": [_poi(id=[])]}})

    with pytest.raises(UpstreamError, match="A1"):
        client.search_place(city="杭州", keywords="博物馆")


# ── 地理编码：类型陷阱 ───────────────────────────────────────────────


def _geo(**over: Any) -> dict[str, Any]:
    base = {
        "province": "浙江省",
        "city": "杭州市",
        "district": "西湖区",
        "adcode": "330106",
        "location": "120.130000,30.260000",
        "level": "兴趣点",
    }
    return {**base, **over}


def test_geocode_parses_a_normal_response():
    client, _ = repo({"geocode/geo": {**OK, "geocodes": [_geo()]}})

    place = client.resolve_place(name="浙江省博物馆")

    assert place is not None
    assert place.adcode == "330106"
    assert place.city == "杭州市"
    assert place.lat == pytest.approx(30.26)


@pytest.mark.parametrize("bad", [[], None, ""])
def test_geocode_survives_the_string_or_array_trap(bad: Any):
    """官方原文：返回值存在时是字符串，不存在时是**数组**。

    直接 `.strip()` 会在字段缺失时抛 `AttributeError`——而**字段缺失是常态**。
    把常态当上游故障处理，错误处理逻辑会整个跑偏。
    """
    client, _ = repo({"geocode/geo": {**OK, "geocodes": [_geo(location=bad)]}})

    assert client.resolve_place(name="某地") is None


def test_geocode_returns_none_when_nothing_matched():
    """**不编一个坐标。** 编出来的中心点会让后续所有距离都错。"""
    client, _ = repo({"geocode/geo": {**OK, "geocodes": []}})

    assert client.resolve_place(name="根本没有这个地方") is None


# ── 路线 ─────────────────────────────────────────────────────────────


def test_driving_route_is_marked_as_road_network():
    """与离线实现的关键差别：这个数字来自路网，**A4 才能拿它断言**。"""
    client, fetch = repo(
        {"direction/driving": {**OK, "route": {"paths": [{"distance": "1200", "duration": "300"}]}}}
    )

    result = client.route(
        origin=LatLon(lat=30.25, lon=120.14),
        destination=LatLon(lat=30.26, lon=120.15),
        mode=RouteMode.DRIVING,
    )

    assert result.basis is RouteBasis.ROAD_NETWORK
    assert (result.distance_m, result.duration_s) == (1200, 300)
    _, params = fetch.calls[0]
    assert params["origin"] == "120.14,30.25", "坐标要按 lon,lat 传"
    assert params["strategy"] == "10", "对齐高德 APP 的默认策略"


def test_transit_is_refused_because_the_interface_cannot_carry_its_params():
    """公交接口要 city 与 cityd，而当前签名里没有它们。

    少传参数让上游按默认城市猜，会得到一条**看起来正常、实际属于别的城市**的
    公交方案——那比报错更糟。
    """
    client, _ = repo({})

    with pytest.raises(CapabilityUnavailable, match="cityd"):
        client.route(
            origin=LatLon(lat=30.25, lon=120.14),
            destination=LatLon(lat=31.23, lon=121.47),
            mode=RouteMode.TRANSIT,
        )


def test_route_without_paths_is_an_upstream_error():
    client, _ = repo({"direction/driving": {**OK, "route": {"paths": []}}})

    with pytest.raises(UpstreamError, match="没有返回可用路径"):
        client.route(
            origin=LatLon(lat=30.0, lon=120.0),
            destination=LatLon(lat=30.1, lon=120.1),
            mode=RouteMode.DRIVING,
        )


# ── 天气 ─────────────────────────────────────────────────────────────


def _forecast(casts: list[dict[str, Any]]) -> dict[str, Any]:
    return {**OK, "forecast": [{"city": "杭州市", "adcode": "330100", "casts": casts}]}


def test_weather_sends_adcode_not_a_city_name():
    """官方明确：`city` **只能传 adcode**。"""
    client, fetch = repo(
        {"weather/weatherInfo": _forecast([{"date": "2026-10-12", "dayweather": "晴",
                                            "daytemp": "24", "nighttemp": "15"}])}
    )

    report = client.weather(adcode="330100", date="2026-10-12")

    assert report.text == "晴"
    assert (report.temp_min_c, report.temp_max_c) == (15.0, 24.0)
    _, params = fetch.calls[0]
    assert params["city"] == "330100"
    assert params["extensions"] == "all"


def test_weather_outside_the_forecast_window_is_a_capability_boundary():
    """「预报只覆盖未来数日」与「那天没有天气」是两件事。"""
    client, _ = repo({"weather/weatherInfo": _forecast([{"date": "2026-10-13"}])})

    with pytest.raises(CapabilityUnavailable, match="不表示那天没有天气"):
        client.weather(adcode="330100", date="1999-01-01")


# ── 两条能力边界 ─────────────────────────────────────────────────────


def test_train_schedule_is_refused_with_the_real_reason():
    client, _ = repo({})

    with pytest.raises(CapabilityUnavailable, match="12306"):
        client.train_schedule(from_city="杭州", to_city="上海", date="2026-10-12")


def test_lookup_area_is_refused_until_its_contract_is_verified():
    client, _ = repo({})

    with pytest.raises(CapabilityUnavailable, match="尚未核到一手文档"):
        client.lookup_area(adcode="330100")


# ── 合规红线：不许缓存 ───────────────────────────────────────────────


def test_identical_calls_hit_upstream_twice_because_caching_is_forbidden():
    """高德协议禁止在平台外缓存或存储其内容。

    所以这里**刻意不做任何缓存**，两次同样的查询就是两次真实请求。这条测试是
    给未来的人看的：**如果哪天有人加了缓存来省配额，这里会红，并告诉他为什么不行。**
    """
    client, fetch = repo({"place/text": {**OK, "pois": [_poi()]}})

    client.search_place(city="杭州", keywords="博物馆")
    client.search_place(city="杭州", keywords="博物馆")

    assert len(fetch.calls) == 2, "缓存高德数据违反其服务协议"


def test_describe_names_the_source_and_says_it_is_live():
    client, _ = repo({})

    text = client.describe()

    assert "高德" in text
    assert "不缓存" in text


# ── 合规红线：不许落盘 ───────────────────────────────────────────────


def test_the_real_implementation_has_no_way_to_persist():
    """纪律 1：不落库真实接口返回的数据。

    高德协议 3.5 条明文禁止「直接存储、缓存或技术手段抓取」其内容，3.4 条禁止用于
    数据集构建。**这条测试读源码而不是断言运行时行为**，因为「代码里没有写盘调用」
    本身没有运行时表现可断言——而它挡的正是「以后有人为了省配额加一层本地缓存」。
    """
    source = (Path(__file__).resolve().parent.parent / "src/data/amap.py").read_text(
        encoding="utf-8"
    )

    for banned in ("sqlite3", "shelve", "pickle", "json.dump", "open("):
        assert banned not in source, f"真实实现里出现了 {banned!r}，它可能把数据落盘了"
