from app.engine import QAItem, score_answer
from app.engine import build_interviewer_reply
from app.engine import detect_interruption


def test_high_pressure_followup_is_harder():
    item = QAItem(question="幂等性是什么", expected_keywords=["唯一", "重试", "去重"])
    ans = "幂等性就是重复请求结果一致。"
    high = score_answer(item, ans, pressure_level="high")
    gentle = score_answer(item, ans, pressure_level="gentle")
    assert "高压追问" in high["follow_up"] or "不达标" in high["feedback"]
    assert "我们放慢一点" in gentle["follow_up"]


def test_interviewer_reply_looks_conversational():
    item = QAItem(question="讲讲幂等性", expected_keywords=["唯一", "重试"])
    eva = score_answer(item, "我会用唯一请求ID和去重表。", pressure_level="standard")
    reply = build_interviewer_reply(item, "我会用唯一请求ID和去重表。", eva, pressure_level="high", interviewer_style="strict", turn_index=1)
    assert "追问" in reply
    assert "90秒" in reply or "高压" in reply


def test_interruption_triggered_in_high_pressure():
    item = QAItem(question="设计权限系统", expected_keywords=["权限", "审计", "最小权限"])
    ans = "我觉得大概做个权限表就行。"
    eva = score_answer(item, ans, pressure_level="high")
    interrupt = detect_interruption(item, ans, eva, pressure_level="high")
    assert interrupt["interrupted"] is True
    assert "打断" in interrupt["message"]
