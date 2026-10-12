"""数据访问层的错误类型。

位置：数据访问层的契约层，与 `types.py` 并列。
可测试性：纯异常定义。
不做的事：不处理错误——**它只负责把「哪种失败」说清楚**，怎么应对是调用方的事。
"""

from __future__ import annotations


class DataAccessError(Exception):
    """数据访问层的基类错误。"""


class MissingCredential(DataAccessError):
    """真实数据源缺少凭据（API key）。

    单独成类而不是并进 `UpstreamError`：**缺凭据是配置问题，不是上游问题**。
    混在一起会让人去查上游状态页，而真正要做的是往 `.env` 里填 key。
    """


class UpstreamError(DataAccessError):
    """上游返回了错误，或响应不符合预期。

    契约：消息里必须带**上游给的具体原因**（错误码与错误描述）。只回灌「失败了」
    没有用——地图服务的错误码是能查的，丢掉它等于丢掉排查起点。
    """


class CapabilityUnavailable(DataAccessError):
    """当前数据源**没有这个能力**，而不是「查了但没有结果」。

    > 这个区分是刻意的：离线快照里没有班次数据，与「这条线路今天没车」是两件事。
    > 如果离线实现返回空列表，上层就无法区分「没查到」与「不存在」——**而
    > 后者会被写成方案里的一句「当日无车」，那是凭空生成的事实。**
    """
