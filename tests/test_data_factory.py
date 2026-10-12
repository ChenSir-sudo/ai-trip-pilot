"""数据源选择（工厂）的测试。

离线：只读环境变量字典，不碰真实环境、不联网。
不做的事：不测各实现自身的行为——那是它们各自的测试文件要覆盖的。
"""

from __future__ import annotations

import pytest

from src.data.amap import AmapRepository
from src.data.errors import MissingCredential
from src.data.factory import (
    AMAP_API_KEY,
    BACKEND_AMAP,
    BACKEND_LOCAL,
    DATA_BACKEND,
    OFFLINE_SNAPSHOT,
    load_data_access,
)
from src.data.local import LocalSnapshotRepository
from test_local_repository import META, PLACES, AREAS, SCHEMA_SQL  # noqa: F401

import sqlite3
from pathlib import Path


@pytest.fixture()
def snapshot(tmp_path: Path) -> str:
    path = tmp_path / "places.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", META.items())
    conn.executemany("INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?)", PLACES)
    conn.executemany("INSERT INTO areas VALUES (?,?,?,?,?,?)", AREAS)
    conn.commit()
    conn.close()
    return str(path)


# ── 纪律 2：两类数据物理不混存 ───────────────────────────────────────


def test_local_backend_returns_exactly_the_offline_implementation(snapshot: str):
    """**「只返回其中一份」是可断言的行为，不是一句承诺。**

    红线 R1 与 architecture §7 的纪律 2 要求两类数据物理不混存。工厂是唯一知道
    「现在用哪一份」的地方，所以这条约束落在这里。
    """
    access = load_data_access({DATA_BACKEND: BACKEND_LOCAL, OFFLINE_SNAPSHOT: snapshot})

    assert isinstance(access, LocalSnapshotRepository)
    assert not isinstance(access, AmapRepository), "绝不能同时是两份实现"


def test_amap_backend_returns_exactly_the_live_implementation():
    access = load_data_access({DATA_BACKEND: BACKEND_AMAP, AMAP_API_KEY: "fake-key"})

    assert isinstance(access, AmapRepository)
    assert not isinstance(access, LocalSnapshotRepository), "绝不能同时是两份实现"


def test_offline_is_the_default_because_it_needs_no_credentials(snapshot: str):
    """默认值必须是**不花钱、不需要凭据**的那一份，否则克隆下来就跑不起来。"""
    assert isinstance(
        load_data_access({OFFLINE_SNAPSHOT: snapshot}), LocalSnapshotRepository
    )


# ── 用错的方式要响亮地失败 ───────────────────────────────────────────


def test_unknown_backend_lists_the_valid_options():
    with pytest.raises(ValueError, match="local"):
        load_data_access({DATA_BACKEND: "nonsense"})


def test_amap_backend_without_a_key_fails_with_instructions():
    with pytest.raises(MissingCredential, match="AMAP_API_KEY"):
        load_data_access({DATA_BACKEND: BACKEND_AMAP, AMAP_API_KEY: ""})


def test_local_backend_without_a_snapshot_says_how_to_get_one(tmp_path: Path):
    from src.data.errors import UpstreamError

    with pytest.raises(UpstreamError, match="fetch_offline_data"):
        load_data_access({DATA_BACKEND: BACKEND_LOCAL, OFFLINE_SNAPSHOT: str(tmp_path / "x.sqlite")})
