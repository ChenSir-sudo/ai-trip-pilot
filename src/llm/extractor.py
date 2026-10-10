"""把出行需求原文抽成槽位：调模型、校验、失败重试一次。

位置：基础设施层。被 `src/graph/builder.py` 的 `extract_slots` 节点调用。
可测试性：模型调用以 `complete` 函数注入，因此可以完全离线测试——
    测试传递假函数，不联网、不需要 key。
不做的事：不判断槽位是否齐全（那是 `src/graph/completeness.py` 的职责）；
    不写存储。

**这是全项目唯一 import openai 的地方**（见 `make_completion_fn`）。
换供应商只改环境变量，图与外壳都不需要动。
"""

from __future__ import annotations

from typing import Any, Callable

from src.llm.config import LLMConfig, load_config
from src.llm.prompts import EXTRACTION_SYSTEM_PROMPT, retry_hint
from src.llm.schema import parse_slots

# 一次用户请求 → 一份原始文本（模型返回的 content）。
CompletionFn = Callable[[list[dict[str, str]]], str]

# 一次抽取最多尝试几次。2 = 首次 + 重试一次。
MAX_ATTEMPTS = 2


class ExtractionError(RuntimeError):
    """没能拿到合法槽位。

    刻意**不做静默降级**：返回空槽位会让 Agent 去问用户「出发城市是哪里」，
    而用户刚刚说过。那比报错糟得多，属于静默丢信息（与红线 R8 同类）。
    """


class OutputTruncated(Exception):
    """输出被 max_tokens 截断。

    单独一个类型，是因为它的处理方式与「模型没按 schema 输出」完全不同：
    重试没有意义（同样的 max_tokens 会再截断一次），必须改配置。
    """


def make_completion_fn(config: LLMConfig) -> CompletionFn:
    """构造真正的模型调用。全项目唯一接触 openai SDK 的地方。

    契约：
      副作用：发起网络请求。
      失败模式：截断抛 OutputTruncated；鉴权/网络错误由 openai SDK 抛出，
          不在这里吞掉——它们的消息本身已经够清楚。
    """

    def complete(messages: list[dict[str, str]]) -> str:
        # 延迟 import：模块可以在没有 openai 的环境里被导入（例如只跑纯逻辑测试）。
        from openai import OpenAI

        client = OpenAI(api_key=config.api_key, base_url=config.base_url)

        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            # JSON Output：配合提示词里的 json 字样与样例，模型会输出合法 JSON。
            response_format={"type": "json_object"},
            max_tokens=config.max_tokens,
            # 思考模式默认打开且 effort=high，对结构化抽取是纯浪费（更慢更贵）。
            # 而且思考模式下 temperature 一类参数会**静默失效**，所以这里显式关闭。
            extra_body={
                "thinking": {"type": "enabled" if config.thinking else "disabled"}
            },
        )

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise OutputTruncated(
                f"输出被 max_tokens={config.max_tokens} 截断，JSON 不完整"
            )
        return choice.message.content or ""

    return complete


def extract_slots_with_llm(raw_request: str, *, complete: CompletionFn) -> dict[str, Any]:
    """把需求原文抽成槽位；校验失败时带上具体错误重试一次。

    契约：
      副作用：通过 `complete` 发起模型调用（最坏情况两次）。
      幂等性：否——重复调用会产生新的模型请求。
      失败模式：抛 ExtractionError。消息里包含每一次尝试的具体错误。
    """
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": raw_request},
    ]

    errors: list[str] = []

    for attempt in range(MAX_ATTEMPTS):
        attempt_messages = list(messages)
        if errors:
            attempt_messages.append({"role": "user", "content": retry_hint(errors[-1])})

        try:
            content = complete(attempt_messages)
        except OutputTruncated as exc:
            # 不重试：同样的 max_tokens 会再截断一次，只是多花一次钱。
            raise ExtractionError(
                f"{exc}。调大 LLM max_tokens（src/llm/config.py 的默认值）后重试。"
            ) from exc

        try:
            return parse_slots(content)
        except ValueError as exc:
            # 空响应、JSON 不合法、schema 不通过都落在这里，可以靠回灌错误重试。
            errors.append(str(exc))

    raise ExtractionError(
        f"连续 {MAX_ATTEMPTS} 次都没能拿到合法槽位；原始需求：{raw_request!r}。\n"
        + "\n".join(f"  第 {i + 1} 次：{message}" for i, message in enumerate(errors))
    )


def make_llm_extractor(
    *, complete: CompletionFn | None = None, config: LLMConfig | None = None
) -> Callable[[str], dict[str, Any]]:
    """构造一个「原文 → 槽位」的抽取器。

    契约：
      副作用：构造时不联网（**延迟**到第一次调用才读配置、建客户端），
          所以 `build_graph()` 在没有 key 的机器上也能成功。
      失败模式：第一次调用时若缺少 key，抛 src.llm.config.ConfigError。
    """
    cached: dict[str, CompletionFn | None] = {"fn": complete}

    def extractor(raw_request: str) -> dict[str, Any]:
        if cached["fn"] is None:
            resolved = config or load_config()
            cached["fn"] = make_completion_fn(resolved)
        return extract_slots_with_llm(raw_request, complete=cached["fn"])  # type: ignore[arg-type]

    return extractor
