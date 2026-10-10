"""模型接入层的测试：schema、提示词、重试逻辑。

**全部离线**：模型调用以 `complete` 函数注入，不联网、不需要 key。
这是依赖注入换来的——`src/llm` 里唯一碰 openai SDK 的地方被参数挡住了。
"""

from __future__ import annotations

import pytest

from src.llm.extractor import (
    ExtractionError,
    OutputTruncated,
    extract_slots_with_llm,
    make_llm_extractor,
)
from src.llm.prompts import EXTRACTION_SYSTEM_PROMPT
from src.llm.schema import Slots, json_schema_for_prompt, parse_slots, validate_slots

# ── schema ────────────────────────────────────────────────────────────


def test_parse_slots_accepts_valid_json():
    assert parse_slots('{"destination_city": "上海", "days": 7}') == {
        "destination_city": "上海",
        "days": 7,
    }


def test_blank_string_becomes_absent():
    """空字符串归一成「没给」——与完整性判定必须用同一个口径。"""
    assert parse_slots('{"origin_city": "   "}') == {}


def test_empty_content_is_a_known_failure():
    """DeepSeek 官方承认 JSON Output 有概率返回空 content，所以这是预期内失败。"""
    with pytest.raises(ValueError, match="空内容"):
        parse_slots("")


def test_invalid_json_reports_position():
    with pytest.raises(ValueError, match="不是合法 JSON"):
        parse_slots('{"days": 7,')


def test_extra_field_is_rejected():
    """多编字段要被看见，不能静默忽略——静默忽略会让提示词悄悄漂移。"""
    with pytest.raises(ValueError, match="schema"):
        parse_slots('{"destination_city": "上海", "vibe": "nice"}')


def test_days_must_be_within_range():
    with pytest.raises(ValueError, match="schema"):
        parse_slots('{"days": 0}')


def test_non_object_json_is_rejected():
    with pytest.raises(ValueError, match="顶层必须是对象"):
        parse_slots("[1, 2, 3]")


# ── 两条输入路径共用同一套校验 ──────────────────────────────────────────


def test_validate_slots_normalises_user_input():
    """用户在澄清里填的永远是字符串，schema 负责归一化。"""
    assert validate_slots({"days": "5"}) == {"days": 5}


def test_validate_slots_rejects_what_a_user_might_type():
    """「五天」不能被当成天数放行——它会一路流进求解器。"""
    with pytest.raises(ValueError, match="schema"):
        validate_slots({"days": "五天"})


def test_both_input_paths_are_checked_the_same_way():
    """模型输出与用户答复必须走同一条校验：否则一个拦、一个不拦。

    这是 review 抓到的真实缺口：`clarify` 只按键过滤，类型校验必须在边界完成。
    """
    payload = {"destination_city": "上海", "vibe": "nice"}

    with pytest.raises(ValueError, match="schema"):
        validate_slots(payload)
    with pytest.raises(ValueError, match="schema"):
        parse_slots('{"destination_city": "上海", "vibe": "nice"}')


# ── 提示词：DeepSeek JSON Output 的硬要求 ──────────────────────────────


def test_prompt_contains_the_word_json_and_an_example():
    """官方要求 prompt 含 json 字样并给出输出样例，否则不保证输出合法 JSON。

    不满足时**不会报错**，只会偶尔拿到坏输出——所以必须由测试守着。
    """
    assert "json" in EXTRACTION_SYSTEM_PROMPT.lower()
    assert '"destination_city"' in EXTRACTION_SYSTEM_PROMPT


def test_prompt_schema_covers_every_field():
    """提示词里的 schema 来自 schema 本身，加字段时会自动跟上。"""
    rendered = json_schema_for_prompt()
    for field in Slots.model_fields:
        assert field in rendered, f"生成的 schema 里缺少字段 {field}"
        assert field in EXTRACTION_SYSTEM_PROMPT, f"提示词里缺少字段 {field}"


# ── 抽取与重试 ────────────────────────────────────────────────────────


def test_returns_slots_on_first_success():
    calls: list[list[dict[str, str]]] = []

    def complete(messages):
        calls.append(messages)
        return '{"destination_city": "上海", "days": 7}'

    assert extract_slots_with_llm("去上海 7 天", complete=complete) == {
        "destination_city": "上海",
        "days": 7,
    }
    assert len(calls) == 1


def test_retries_once_with_the_concrete_error():
    """重试必须带上具体原因——只说「失败了」等于让模型重掷一次骰子。"""
    calls: list[list[dict[str, str]]] = []

    def complete(messages):
        calls.append(messages)
        if len(calls) == 1:
            return '{"days": "七天"}'
        return '{"days": 7}'

    assert extract_slots_with_llm("玩七天", complete=complete) == {"days": 7}
    assert len(calls) == 2

    hint = calls[1][-1]["content"]
    assert "不合法" in hint
    assert "days" in hint, "回灌的提示里应指出具体是哪个字段"


def test_gives_up_after_one_retry_and_reports_every_attempt():
    """不静默降级：两次都失败就明确报错，并带上每一次的原因。"""

    def complete(messages):
        return "not json at all"

    with pytest.raises(ExtractionError) as excinfo:
        extract_slots_with_llm("随便什么", complete=complete)

    message = str(excinfo.value)
    assert "第 1 次" in message
    assert "第 2 次" in message


def test_truncation_is_not_retried():
    """截断是配置问题：重试只会再截断一次、再花一次钱。"""
    calls: list[list[dict[str, str]]] = []

    def complete(messages):
        calls.append(messages)
        raise OutputTruncated("输出被 max_tokens=1024 截断")

    with pytest.raises(ExtractionError, match="max_tokens"):
        extract_slots_with_llm("很长的需求", complete=complete)

    assert len(calls) == 1, "截断不该触发重试"


def test_llm_extractor_needs_no_config_when_complete_is_injected():
    """注入假调用时连配置都不该读——否则离线测试会依赖环境变量。"""
    extractor = make_llm_extractor(complete=lambda messages: '{"days": 3}')

    assert extractor("玩三天") == {"days": 3}
