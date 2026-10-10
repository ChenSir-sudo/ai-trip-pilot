"""模型接入配置：从环境变量或 .env 读取，默认指向 DeepSeek。

位置：基础设施层。
可测试性：纯函数 + 环境变量读取，不联网。
不做的事：不创建客户端——配置与连接分开，图在构建时不需要网络。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 默认值指向 DeepSeek。换供应商时只改环境变量，不动代码。
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"

# 仓库根目录下的 .env（已被 .gitignore 排除）。
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class ConfigError(RuntimeError):
    """配置缺失或不可用。消息里必须写清怎么修。"""


@dataclass(frozen=True)
class LLMConfig:
    """一次模型接入所需的全部配置。

    `thinking` 默认关闭：结构化抽取不需要思维链，开着更慢更贵；
    而且**思考模式下 temperature 等参数会静默失效**（设置不报错但不生效）。
    """

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    thinking: bool = False
    max_tokens: int = 1024

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(*, require_key: bool = True) -> LLMConfig:
    """读取配置。`require_key=False` 时允许没有 key，用于只检查默认值。

    契约：
      副作用：读取 .env（若存在）并写入进程环境变量。这是 python-dotenv 的行为，
          刻意保留——不写回环境变量的话，子进程与测试都拿不到这些值。
      幂等性：是。
      失败模式：缺少 api_key 且 `require_key=True` 时抛 ConfigError，
          消息中给出修复方式，而不是让调用方对着 401 猜。

    兼容 `DEEPSEEK_API_KEY`：官方文档的示例用这个名字，用户很可能已经导出过它。
    """
    load_dotenv(_ENV_FILE, override=False)

    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""

    config = LLMConfig(
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL,
        model=os.environ.get("LLM_MODEL") or DEFAULT_MODEL,
        thinking=_as_bool(os.environ.get("LLM_THINKING"), default=False),
    )

    if require_key and not config.is_configured:
        raise ConfigError(
            "未设置 LLM_API_KEY。\n"
            "  方式一：cp .env.example .env，然后填入 LLM_API_KEY=...\n"
            "  方式二：export LLM_API_KEY=...\n"
            "  也接受 DEEPSEEK_API_KEY 这个变量名。"
        )

    return config
