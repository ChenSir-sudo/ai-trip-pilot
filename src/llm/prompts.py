"""抽取用的提示词。

位置：基础设施层。
可测试性：纯字符串，不联网。
不做的事：不做校验——schema 才是唯一的裁判。提示词的职责是让模型一次就对；
    对不了由 extractor 回灌具体错误重试。

DeepSeek 的 JSON Output 有两条硬要求（官方文档）：
  1. prompt 中必须含 `json` 字样，并给出期望的输出样例；
  2. 必须合理设置 `max_tokens` 防止 JSON 被截断（在 config 里设）。
第 1 条不满足时不会报错，只会得到一个不保证合法的字符串——失败现场很难看懂。

字段清单来自 schema 本身（`json_schema_for_prompt()`），所以**加字段时提示词会自动
跟上**，不会出现「schema 改了、提示词忘了改」的静默漂移。
"""

from __future__ import annotations

from src.llm.schema import json_schema_for_prompt

EXTRACTION_SYSTEM_PROMPT = f"""你是出行需求解析器。把用户的一句话需求解析成 json。

只输出 json 本身：不要解释、不要 markdown 代码块、不要多余字段。

按下面的 JSON Schema 输出：
{json_schema_for_prompt()}

字段语义与取值约定：
- origin_city / destination_city：城市名，例如「杭州」「上海」。
- depart_date：YYYY-MM-DD。用户只说「7 月」时不要编造具体日期，省略它。
- days：出行天数，整数。用户说「玩 5 天」就是 5。
- budget：预算上限，人民币整数。用户说「预算 6000」就是 6000。
- companions：同行人类别数组，例如 ["儿童", "老人"]。

示例输入：从杭州去上海玩 5 天，带一个 5 岁的孩子，预算 8000
示例 json 输出：
{{"origin_city": "杭州", "destination_city": "上海", "days": 5, "budget": 8000, "companions": ["儿童"]}}

示例输入：周末想在家附近逛逛
示例 json 输出：{{}}

最重要的一条：**没有明确提到的字段一律省略，不要猜。**
缺什么由后续流程去问用户；你编出来的城市会让整份方案建立在错误的前提上。
"""


def retry_hint(error: str) -> str:
    """把上一次的具体错误回灌给模型。

    契约：纯函数。
    为什么不只回灌「失败了」：模型不知道错在哪就只能重掷一次骰子，
    而带上「days 必须是整数」这类信息，第二次基本能对。
    """
    return (
        f"上一次的输出不合法：{error}\n"
        "请只输出一个合法的 json 对象，不要任何解释或代码块包裹。"
    )
