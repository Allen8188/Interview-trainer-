import importlib
import os


def _load_storage_with_tmp(tmp_path):
    os.environ["IT_DATA_DIR"] = str(tmp_path)
    import app.storage as storage

    return importlib.reload(storage)


def test_materials_cache_roundtrip(tmp_path):
    storage = _load_storage_with_tmp(tmp_path)
    company = "CacheCo"
    role = "Backend"
    items = [{"title": "repo/a", "url": "https://example.com", "summary": "x"}]
    storage.set_materials_cache(company, role, items)
    got = storage.get_materials_cache(company, role, ttl_hours=24)
    assert got is not None
    assert got[0]["title"] == "repo/a"


def test_rename_snapshot(tmp_path):
    storage = _load_storage_with_tmp(tmp_path)
    sid = "rename-test-session"
    storage.save_session_snapshot({"id": sid, "session_label": "old"})
    ok = storage.rename_session_snapshot(sid, "new-label")
    assert ok is True


def test_redaction_masks_pii(tmp_path):
    storage = _load_storage_with_tmp(tmp_path)
    payload = {
        "id": "pii-test",
        "resume_text": "电话 13812345678 邮箱 a@b.com 身份证 11010519491231002X",
        "history": [{"answer": "联系我13812345678", "interviewer_reply": "ok", "interruption_message": ""}],
        "dialog": [{"role": "candidate", "text": "邮箱 a@b.com"}],
    }
    data = storage.serialize_session(payload, redact=True)
    assert "[PHONE]" in data["resume_text"]
    assert "[EMAIL]" in data["resume_text"]
    assert "[ID]" in data["resume_text"]


def test_export_and_delete_snapshot(tmp_path):
    storage = _load_storage_with_tmp(tmp_path)
    sid = "exp-del"
    storage.save_session_snapshot({"id": sid, "session_label": "x"})
    out = storage.export_session_snapshot(sid)
    assert out is not None and out.exists()
    deleted = storage.delete_session_snapshot(sid)
    assert deleted is True


def test_api_key_not_persisted_in_snapshot(tmp_path):
    storage = _load_storage_with_tmp(tmp_path)
    payload = {"id": "k1", "llm_api_key": "sk-secret", "resume_text": "x"}
    data = storage.serialize_session(payload, redact=True)
    assert "llm_api_key" not in data
