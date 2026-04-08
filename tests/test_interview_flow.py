from fastapi.testclient import TestClient

from app.main import app


def test_empty_answer_does_not_advance_question():
    client = TestClient(app)
    create = client.post(
        "/api/session",
        json={
            "resume_text": "熟练掌握 Fortran，Python，MPI并行计算\n项目：做过MPI并行优化",
            "company": "Acme",
            "role": "Backend Intern",
            "rounds": 3,
            "mode": "mixed",
        },
    )
    assert create.status_code == 200
    data = create.json()
    sid = data["session_id"]
    q1 = data["question"]["question"]

    ans = client.post(f"/api/session/{sid}/answer", json={"answer": ""})
    assert ans.status_code == 200
    payload = ans.json()
    assert payload["done"] is False
    assert payload["next_question"]["question"] == q1
    assert payload["evaluation"]["repeat_current"] is True


def test_short_garbage_answer_does_not_advance_question():
    client = TestClient(app)
    create = client.post(
        "/api/session",
        json={
            "resume_text": "熟练掌握 Fortran，Python，MPI并行计算\n项目：做过MPI并行优化",
            "company": "Acme",
            "role": "Backend Intern",
            "rounds": 3,
            "mode": "mixed",
        },
    )
    assert create.status_code == 200
    data = create.json()
    sid = data["session_id"]
    q1 = data["question"]["question"]

    ans = client.post(f"/api/session/{sid}/answer", json={"answer": "3"})
    assert ans.status_code == 200
    payload = ans.json()
    assert payload["done"] is False
    assert payload["next_question"]["question"] == q1
    assert payload["evaluation"]["repeat_current"] is True
