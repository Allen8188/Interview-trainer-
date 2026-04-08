from app.engine import suggest_session_label


def test_suggest_session_label_auto_and_custom():
    auto = suggest_session_label("Acme", "Backend Intern", "backend", "python mpi", custom_label="")
    assert "Acme" in auto
    custom = suggest_session_label("Acme", "Backend Intern", "backend", "python mpi", custom_label="我的第1轮")
    assert custom == "我的第1轮"
