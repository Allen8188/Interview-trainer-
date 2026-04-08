from app.main import _llm_reply_quality_ok


def test_llm_reply_quality_gate():
    ok, reason = _llm_reply_quality_ok("补充反馈。追问：你如何做指标回收？")
    assert ok is True and reason == "ok"

    ok2, reason2 = _llm_reply_quality_ok("抱歉，我无法回答")
    assert ok2 is False
    assert reason2 in {"too_short", "generic_or_refusal", "no_followup"}
