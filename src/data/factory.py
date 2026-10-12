"""按环境变量选择数据源。

位置：基础设施层的**唯一一处**知道「现在用的是哪个数据源」的地方。图与入口只拿
    到 `DataAccess`，不知道自己背后是离线快照还是地图服务（architecture.md §7）。
可测试性：读环境变量并把 `env` 作为参数注入，测不必碰真实环境、不联网。
不做的事：不重试、不缓存、**不把两个源混起来**。两类数据物理不混存是红线 R1 的
    一部分，所以这里只可能返回其中一份。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv

from src.data.amap import AmapRepository
from src.data.base import DataAccess
from src.data.local import LocalSnapshotRepository

# 环境变量名。`DATA_BACKEND` 决定用哪一份，默认离线——**默认值必须是不花钱、
# 不需要凭据的那一份**，否则克隆下来就跑不起来。
DATA_BACKEND = "DATA_BACKEND"
OFFLINE_SNAPSHOT = "OFFLINE_SNAPSHOT"
AMAP_API_KEY = "AMAP_API_KEY"

BACKEND_LOCAL = "local"
BACKEND_AMAP = "amap"

DEFAULT_SNAPSHOT = Path("data/offline/places.sqlite")

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


def load_data_access(env: Mapping[str, str] | None = None) -> DataAccess:
    """按 `DATA_BACKEND` 造一份数据访问实现。

    契约：
      副作用：`env` 为 `None` 时读取仓库根目录的 `.env`（若存在）并写回进程环境变量
          ——这是 python-dotenv 的行为，刻意保留，否则子进程拿不到这些值。
      失败模式：未知的 `DATA_BACKEND` 抛 `ValueError` 并列出可选值；
          选 `amap` 但没填 key 时抛 `MissingCredential`（由实现自己抛）。
    """
    if env is None:
        load_dotenv(_ENV_FILE, override=False)
        env = os.environ

    backend = (env.get(DATA_BACKEND) or BACKEND_LOCAL).strip().lower()

    if backend == BACKEND_LOCAL:
        snapshot = env.get(OFFLINE_SNAPSHOT) or str(DEFAULT_SNAPSHOT)
        return LocalSnapshotRepository(snapshot)
    if backend == BACKEND_AMAP:
        return AmapRepository(env.get(AMAP_API_KEY) or "")

    raise ValueError(
        f"未知的 {DATA_BACKEND}={backend!r}；可选 {BACKEND_LOCAL} / {BACKEND_AMAP}。"
    )
