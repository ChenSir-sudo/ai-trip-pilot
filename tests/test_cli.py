"""命令行入口的测试：答复收集与就地校验。

不联网：`ask_for_fields` 只读标准输入，不碰模型。
"""

from __future__ import annotations

from src.main import ask_for_fields

PAYLOAD = {
    "question": "开始规划前还需要确认：出发城市。",
    "fields": [{"key": "origin_city", "label": "出发城市"}],
}


def _feed(monkeypatch, replies: list[str]) -> None:
    """把 input() 换成按顺序喂固定答复。"""
    replies_iter = iter(replies)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies_iter))


def test_collects_the_answer(monkeypatch):
    _feed(monkeypatch, ["杭州"])

    assert ask_for_fields(PAYLOAD) == {"origin_city": "杭州"}


def test_reprompts_when_the_answer_does_not_fit_the_schema(monkeypatch, capsys):
    """填错就地重问，不让不合格式的值进入状态。

    这条守着 review 抓到的问题：答复路径原本绕过 schema，`days` 填「五天」
    会变成一个字符串天数流进后面的求解器。
    """
    payload = {
        "question": "开始规划前还需要确认：天数。",
        "fields": [{"key": "days", "label": "天数"}],
    }
    _feed(monkeypatch, ["五天", "5"])

    assert ask_for_fields(payload) == {"days": 5}, "字符串数字应被归一化成整数"
    assert "不合法" in capsys.readouterr().out, "应当告诉用户哪里填错了"


def test_empty_answer_is_asked_again_locally(monkeypatch, capsys):
    """一项都不填时在本地重问，不必往图里白跑一趟。"""
    _feed(monkeypatch, ["", "杭州"])

    assert ask_for_fields(PAYLOAD) == {"origin_city": "杭州"}
    assert "至少填一项" in capsys.readouterr().out


def test_skipped_field_is_omitted(monkeypatch):
    """回车跳过就是不填——空字符串不该进入槽位。"""
    payload = {
        "question": "q",
        "fields": [
            {"key": "origin_city", "label": "出发城市"},
            {"key": "budget", "label": "预算"},
        ],
    }
    _feed(monkeypatch, ["杭州", ""])

    assert ask_for_fields(payload) == {"origin_city": "杭州"}
