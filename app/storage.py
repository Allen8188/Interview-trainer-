from __future__ import annotations

import json
import os
import re
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = Path.home() / ".interview-trainer" / "data"
DATA_DIR = Path(os.environ.get("IT_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser()
SESSIONS_DIR = DATA_DIR / "sessions"
CACHE_FILE = DATA_DIR / "materials_cache.json"
EXPORTS_DIR = DATA_DIR / "exports"
PRIVACY_REDACT = os.environ.get("IT_PRIVACY_REDACT", "1") != "0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _mask_text(text: str) -> str:
    if not text:
        return text
    masked = text
    masked = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL]", masked)
    masked = re.sub(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)", "[PHONE]", masked)
    masked = re.sub(r"\b\d{15}(?:\d{2}[0-9Xx])?\b", "[ID]", masked)
    return masked


def redact_text(text: str) -> str:
    return _mask_text(text)


def _mask_dialog(dialog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in dialog:
        out.append({"role": item.get("role", ""), "text": _mask_text(item.get("text", ""))})
    return out


def _mask_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in history:
        copy = dict(row)
        copy["answer"] = _mask_text(copy.get("answer", ""))
        copy["interviewer_reply"] = _mask_text(copy.get("interviewer_reply", ""))
        copy["interruption_message"] = _mask_text(copy.get("interruption_message", ""))
        out.append(copy)
    return out


def serialize_session(session: dict[str, Any], redact: bool | None = None) -> dict[str, Any]:
    if redact is None:
        redact = PRIVACY_REDACT

    bank = []
    for item in session.get("bank", []):
        if hasattr(item, "question"):
            bank.append(
                {
                    "question": item.question,
                    "expected_keywords": list(getattr(item, "expected_keywords", [])),
                    "category": getattr(item, "category", "general"),
                }
            )
        elif isinstance(item, dict):
            bank.append(item)

    resume_text = session.get("resume_text", "")
    history = session.get("history", [])
    dialog = session.get("dialog", [])
    if redact:
        resume_text = _mask_text(resume_text)
        history = _mask_history(history)
        dialog = _mask_dialog(dialog)

    return {
        "id": session.get("id"),
        "company": session.get("company", ""),
        "role": session.get("role", ""),
        "resume_text": resume_text,
        "cursor": session.get("cursor", 0),
        "round_limit": session.get("round_limit", 8),
        "mode": session.get("mode", "mixed"),
        "pressure_level": session.get("pressure_level", "standard"),
        "interviewer_style": session.get("interviewer_style", "professional"),
        "session_label": session.get("session_label", "面试练习会话"),
        "history": history,
        "dialog": dialog,
        "materials": session.get("materials", []),
        "bank": bank,
        "created_at": session.get("created_at", _now_iso()),
        "updated_at": _now_iso(),
        "redacted": bool(redact),
    }


def save_session_snapshot(session: dict[str, Any]) -> None:
    _ensure_dirs()
    payload = serialize_session(session)
    sid = payload.get("id")
    if not sid:
        return
    _write_json(SESSIONS_DIR / f"{sid}.json", payload)


def delete_session_snapshot(session_id: str) -> bool:
    _ensure_dirs()
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True


def load_session_snapshot(session_id: str) -> dict[str, Any] | None:
    _ensure_dirs()
    path = SESSIONS_DIR / f"{session_id}.json"
    data = _read_json(path, None)
    if not data:
        return None
    return data


def list_session_snapshots(limit: int = 50) -> list[dict[str, Any]]:
    _ensure_dirs()
    files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    items = []
    for fp in files[:limit]:
        data = _read_json(fp, {})
        if not data:
            continue
        items.append(
            {
                "id": data.get("id", fp.stem),
                "company": data.get("company", ""),
                "role": data.get("role", ""),
                "mode": data.get("mode", "mixed"),
                "pressure_level": data.get("pressure_level", "standard"),
                "session_label": data.get("session_label", "面试练习会话"),
                "updated_at": data.get("updated_at"),
                "history_count": len(data.get("history", [])),
                "redacted": bool(data.get("redacted", False)),
            }
        )
    return items


def rename_session_snapshot(session_id: str, new_label: str) -> bool:
    _ensure_dirs()
    path = SESSIONS_DIR / f"{session_id}.json"
    data = _read_json(path, None)
    if not data:
        return False
    data["session_label"] = (new_label or "").strip()[:80] or "面试练习会话"
    data["updated_at"] = _now_iso()
    _write_json(path, data)
    return True


def export_session_snapshot(session_id: str) -> Path | None:
    _ensure_dirs()
    src = SESSIONS_DIR / f"{session_id}.json"
    data = _read_json(src, None)
    if not data:
        return None
    out = EXPORTS_DIR / f"session-{session_id}.json"
    _write_json(out, data)
    return out


def import_session_snapshot(payload: dict[str, Any], new_id: str) -> Path:
    _ensure_dirs()
    payload = dict(payload)
    payload["id"] = new_id
    payload["updated_at"] = _now_iso()
    out = SESSIONS_DIR / f"{new_id}.json"
    _write_json(out, payload)
    return out


def _resume_fingerprint(resume_text: str, n: int = 320) -> str:
    norm = (resume_text or "").strip().lower()[:n]
    if not norm:
        return "no-resume"
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def _cache_key(company: str, role: str, resume_text: str = "") -> str:
    return f"{company.strip().lower()}::{role.strip().lower()}::{_resume_fingerprint(resume_text)}"


def get_materials_cache(
    company: str,
    role: str,
    resume_text: str = "",
    ttl_hours: int = 24,
) -> list[dict[str, str]] | None:
    _ensure_dirs()
    raw = _read_json(CACHE_FILE, {})
    key = _cache_key(company, role, resume_text=resume_text)
    entry = raw.get(key)
    if not entry:
        return None
    updated_at = entry.get("updated_at")
    try:
        ts = datetime.fromisoformat(updated_at)
    except Exception:
        return None
    if datetime.now(timezone.utc) - ts > timedelta(hours=ttl_hours):
        return None
    return entry.get("items", [])


def set_materials_cache(company: str, role: str, items: list[dict[str, str]], resume_text: str = "") -> None:
    _ensure_dirs()
    raw = _read_json(CACHE_FILE, {})
    raw[_cache_key(company, role, resume_text=resume_text)] = {"updated_at": _now_iso(), "items": items}
    _write_json(CACHE_FILE, raw)
