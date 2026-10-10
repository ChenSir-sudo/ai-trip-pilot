"""槽位的严格 schema。

位置：基础设施层。这是「模型输出」与「图的状态」之间的唯一契约。
可测试性：纯数据模型，不联网。
不做的事：不判断必需槽位是否齐全（那是 src/graph/completeness.py 的职责）。
    这里只管「模型给的这一份数据本身合不合法」。

它一次解决三件事：
  1. 定义槽位的形状（唯一的真相）；
  2. 生成给模型看的 JSON Schema（见 `json_schema_for_prompt`）；
  3. 校验模型输出（见 `parse_slots`）。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# 与 src/graph/completeness.py 里的槽位键保持一致。
FIELD_DESCRIPTIONS: dict[str, str] = {
    "origin_city": "出发城市，例如「杭州」",
    "destination_city": "目的城市，例如「上海」",
    "depart_date": "出发日期，格式 YYYY-MM-DD",
    "days": "出行天数，整数",
    "budget": "预算上限，人民币整数",
    "companions": "同行人类别，例如 ['儿童']",
}


class Slots(BaseModel):
    """一次抽取产出的槽位。

    `extra="forbid"` 是刻意的：模型多编字段就是要被看见。
    静默忽略会让提示词悄悄漂移，而漂移是没法测的。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    origin_city: str | None = None
    destination_city: str | None = None
    depart_date: str | None = None
    days: int | None = Field(default=None, ge=1, le=365)
    budget: int | None = Field(default=None, ge=0)
    companions: list[str] | None = None

    @field_validator("origin_city", "destination_city", "depart_date", mode="after")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        """把空字符串归一成 None。

        与完整性判定的口径对齐：`{"origin_city": ""}` 和「没给」在规划上等价，
        两边必须用同一个判断，否则会出现「schema 认为填了、判定认为缺」的分歧。
        """
        return value or None


def json_schema_for_prompt() -> str:
    """生成塞进提示词的 JSON 结构说明。

    用法：把返回值原样放进 system prompt。它来自 schema 本身，
    所以**加字段时提示词会自动跟上**，不会两处维护。
    """
    return json.dumps(Slots.model_json_schema(), ensure_ascii=False, indent=2)


def parse_slots(raw: str) -> dict[str, Any]:
    """把模型返回的原始字符串解析成槽位 dict。

    契约：
      副作用：无。纯函数。
      幂等性：是。
      失败模式：抛 ValueError，消息里带上**具体原因**（空响应 / JSON 不合法 /
          schema 不通过）。调用方拿这个原因去重试——只回灌「失败了」没有用。
    """
    if not raw or not raw.strip():
        # DeepSeek 官方文档明确写了「使用 JSON Output 时有概率返回空 content」，
        # 所以这是预期内的失败，不是异常情况。
        raise ValueError("模型返回了空内容（JSON Output 已知偶发）")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"返回的不是合法 JSON：{exc.msg}（位置 {exc.pos}）") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"返回的 JSON 顶层必须是对象，实际是 {type(payload).__name__}")

    try:
        return Slots.model_validate(payload).model_dump(exclude_none=True)
    except ValidationError as exc:
        # 只留前三条，避免把重试提示词撑爆。
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()[:3]
        )
        raise ValueError(f"字段不符合 schema：{details}") from exc
