from __future__ import annotations

import os
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import (
    QAItem,
    build_profile_seed_materials,
    build_interviewer_reply,
    build_question_bank,
    detect_interruption,
    extract_text_from_docx_bytes,
    fetch_external_interview_questions,
    fetch_github_materials,
    fetch_web_interview_materials,
    ideal_answer_template,
    normalize_resume_text,
    score_answer,
    suggest_session_label,
)
from .stt import STTUnavailableError, transcribe_audio_bytes
from .llm import generate_interviewer_reply_via_openai_compatible
from .storage import (
    DATA_DIR,
    delete_session_snapshot,
    export_session_snapshot,
    get_materials_cache,
    import_session_snapshot,
    list_session_snapshots,
    load_session_snapshot,
    rename_session_snapshot,
    redact_text,
    save_session_snapshot,
    set_materials_cache,
)


class SessionCreateRequest(BaseModel):
    resume_text: str = Field(default="")
    company: str = Field(default="")
    role: str = Field(default="")
    rounds: int = Field(default=14, ge=3, le=24)
    target_minutes: int = Field(default=35, ge=15, le=90)
    mode: str = Field(default="mixed")
    pressure_level: str = Field(default="standard")
    interviewer_style: str = Field(default="professional")
    session_label: str = Field(default="")
    llm_enabled: bool = Field(default=False)
    llm_provider: str = Field(default="openai_compatible")
    llm_model: str = Field(default="gpt-4o-mini")
    llm_base_url: str = Field(default="https://api.openai.com/v1")
    llm_api_key: str = Field(default="")
    llm_send_raw: bool = Field(default=False)
    llm_mode: str = Field(default="assist_only")


class AnswerRequest(BaseModel):
    answer: str


class STTResponse(BaseModel):
    text: str
    engine: str = "local_whisper"


class RenameRequest(BaseModel):
    session_label: str


class ImportHistoryResponse(BaseModel):
    session_id: str
    restored_from: str


class LLMConfigRequest(BaseModel):
    llm_enabled: bool = False
    llm_provider: str = "openai_compatible"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_send_raw: bool = False
    llm_mode: str = "assist_only"


app = FastAPI(title="Interview Trainer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


SESSIONS: dict[str, dict[str, Any]] = {}


def _effective_round_count(session: dict[str, Any]) -> int:
    return sum(1 for h in session.get("history", []) if h.get("count_for_round", True))


def _pick_question(session: dict[str, Any]) -> QAItem | None:
    idx = session["cursor"]
    if idx >= len(session["bank"]):
        return None
    return session["bank"][idx]


def _bank_to_items(bank_data: list[dict[str, Any]]) -> list[QAItem]:
    items = []
    for row in bank_data:
        items.append(
            QAItem(
                question=row.get("question", ""),
                expected_keywords=row.get("expected_keywords", []),
                category=row.get("category", "general"),
                rubric_points=row.get("rubric_points", []),
            )
        )
    return items


def _llm_reply_quality_ok(text: str) -> tuple[bool, str]:
    t = (text or "").strip()
    if not t:
        return False, "empty"
    if len(t) < 16:
        return False, "too_short"
    if len(t) > 220:
        return False, "too_long"
    if "追问" not in t and "?" not in t and "？" not in t:
        return False, "no_followup"
    bad_tokens = ["作为AI", "我无法", "无法回答", "抱歉"]
    if any(tok in t for tok in bad_tokens):
        return False, "generic_or_refusal"
    return True, "ok"


@app.get("/")
def root() -> FileResponse:
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="web/index.html not found")
    return FileResponse(index)


@app.get("/api/privacy/status")
def privacy_status() -> dict[str, Any]:
    return {
        "data_dir": str(DATA_DIR),
        "redaction_enabled": True,
        "notes": "持久化记录默认已脱敏（邮箱/手机号/证件号）。",
    }


@app.get("/api/privacy/wizard")
def privacy_wizard() -> dict[str, Any]:
    return {
        "steps": [
            "默认使用本地规则面试能力（不出网）",
            "若启用大模型增强，请使用用户自己的 API key",
            "默认对发送给大模型的文本做脱敏",
            "API key 只保存在内存会话，不写入磁盘历史",
        ],
        "defaults": {
            "llm_enabled": False,
            "llm_send_raw": False,
            "redaction_enabled": True,
        },
    }


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)) -> dict[str, str]:
    content = await file.read()
    name = (file.filename or "").lower()

    if name.endswith(".docx"):
        text = extract_text_from_docx_bytes(content)
    elif name.endswith(".txt"):
        text = content.decode("utf-8", "ignore")
    else:
        raise HTTPException(status_code=400, detail="仅支持 .docx 或 .txt")

    text = normalize_resume_text(text)
    if not text:
        raise HTTPException(status_code=400, detail="解析后简历为空")

    return {"resume_text": text}


@app.post("/api/session")
async def create_session(req: SessionCreateRequest) -> dict[str, Any]:
    resume_text = normalize_resume_text(req.resume_text)
    if not resume_text:
        raise HTTPException(status_code=400, detail="请先输入或上传简历文本")

    bank = build_question_bank(resume_text, req.company, req.role, mode=req.mode)
    try:
        external_qs = await fetch_external_interview_questions(
            req.company, req.role, resume_text=resume_text, limit=6
        )
    except Exception:
        external_qs = []
    if external_qs:
        ext_items: list[QAItem] = []
        for q in external_qs:
            ext_items.append(
                QAItem(
                    question=f"外部资料追问：{q}",
                    expected_keywords=[],
                    category="external_domain",
                    rubric_points=[],
                )
            )
        # Keep resume deep-dive first, then blend external domain questions.
        resume_count = 0
        for item in bank:
            if item.category == "resume_deep_dive":
                resume_count += 1
        insert_at = min(max(2, resume_count), len(bank))
        bank[insert_at:insert_at] = ext_items
    if not bank:
        raise HTTPException(status_code=400, detail="未生成题目，请检查输入")

    suggested_rounds = min(24, max(12, req.target_minutes // 2))
    round_limit = req.rounds
    if req.mode == "mixed" and req.rounds < suggested_rounds:
        round_limit = suggested_rounds

    session_label = suggest_session_label(
        req.company, req.role, req.mode, resume_text, custom_label=req.session_label
    )

    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "id": session_id,
        "company": req.company,
        "role": req.role,
        "resume_text": resume_text,
        "bank": bank,
        "cursor": 0,
        "round_limit": round_limit,
        "target_minutes": req.target_minutes,
        "mode": req.mode,
        "pressure_level": req.pressure_level,
        "interviewer_style": req.interviewer_style,
        "session_label": session_label,
        "llm_enabled": bool(req.llm_enabled),
        "llm_provider": req.llm_provider,
        "llm_model": req.llm_model,
        "llm_base_url": req.llm_base_url,
        "llm_api_key": req.llm_api_key,
        "llm_send_raw": bool(req.llm_send_raw),
        "llm_mode": req.llm_mode,
        "history": [],
        "dialog": [],
        "materials": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    first = _pick_question(SESSIONS[session_id])
    if first:
        SESSIONS[session_id]["dialog"].append(
            {"role": "interviewer", "text": f"我们开始第一题：{first.question}"}
        )
    save_session_snapshot(SESSIONS[session_id])
    return {
        "session_id": session_id,
        "mode": req.mode,
        "target_minutes": req.target_minutes,
        "round_limit": round_limit,
        "suggested_rounds": suggested_rounds,
        "pressure_level": req.pressure_level,
        "interviewer_style": req.interviewer_style,
        "session_label": session_label,
        "llm_enabled": bool(req.llm_enabled),
        "llm_provider": req.llm_provider,
        "llm_model": req.llm_model,
        "llm_send_raw": bool(req.llm_send_raw),
        "llm_mode": req.llm_mode,
        "question": asdict(first) if first else None,
        "total_candidates": len(bank),
        "dialog": SESSIONS[session_id]["dialog"],
    }


@app.post("/api/stt", response_model=STTResponse)
async def stt_transcribe(file: UploadFile = File(...), language: str = "zh") -> STTResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="音频为空")
    try:
        text = transcribe_audio_bytes(content, filename=file.filename or "audio.webm", language=language)
    except STTUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"转写失败: {exc}") from exc
    return STTResponse(text=text)


@app.post("/api/session/{session_id}/materials")
async def load_materials(session_id: str, refresh: bool = False) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    cached = None if refresh else get_materials_cache(
        session["company"],
        session["role"],
        resume_text=session.get("resume_text", ""),
        ttl_hours=24,
    )
    if cached:
        session["materials"] = cached
        save_session_snapshot(session)
        source_counts: dict[str, int] = {}
        for m in cached:
            src = m.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1
        return {"materials": cached, "cached": True, "source_counts": source_counts}

    github_mats = await fetch_github_materials(
        session["company"], session["role"], resume_text=session.get("resume_text", ""), limit=5
    )
    web_mats = await fetch_web_interview_materials(
        session["company"], session["role"], resume_text=session.get("resume_text", ""), limit=5
    )
    merged = []
    seen_url = set()
    for m in github_mats + web_mats:
        url = m.get("url", "")
        if not url or url in seen_url:
            continue
        seen_url.add(url)
        merged.append(m)
    mats = merged[:8]
    fallback_used = False
    if not mats:
        # second pass: retry with the same profile to avoid drifting into unrelated generic material.
        fallback_used = True
        github_mats = await fetch_github_materials(
            session["company"], session["role"], resume_text=session.get("resume_text", ""), limit=6
        )
        web_mats = await fetch_web_interview_materials(
            session["company"], session["role"], resume_text=session.get("resume_text", ""), limit=6
        )
        merged = []
        seen_url = set()
        for m in github_mats + web_mats:
            url = m.get("url", "")
            if not url or url in seen_url:
                continue
            seen_url.add(url)
            merged.append(m)
        mats = merged[:8]
    if not mats:
        mats = build_profile_seed_materials(
            session["company"], session["role"], resume_text=session.get("resume_text", ""), limit=6
        )
    session["materials"] = mats
    set_materials_cache(
        session["company"],
        session["role"],
        mats,
        resume_text=session.get("resume_text", ""),
    )
    save_session_snapshot(session)
    source_counts: dict[str, int] = {}
    for m in mats:
        src = m.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
    diagnostic = {
        "fallback_used": fallback_used,
        "company": session.get("company", ""),
        "role": session.get("role", ""),
        "resume_keywords_applied": bool(session.get("resume_text", "").strip()),
    }
    return {"materials": mats, "cached": False, "source_counts": source_counts, "diagnostic": diagnostic}


@app.get("/api/session/{session_id}/question")
def get_question(session_id: str) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    if _effective_round_count(session) >= session["round_limit"]:
        return {"done": True, "question": None}

    q = _pick_question(session)
    return {"done": q is None, "question": asdict(q) if q else None}


@app.patch("/api/session/{session_id}/llm")
def update_session_llm(session_id: str, req: LLMConfigRequest) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    session["llm_enabled"] = bool(req.llm_enabled)
    session["llm_provider"] = req.llm_provider
    session["llm_model"] = req.llm_model
    session["llm_base_url"] = req.llm_base_url
    session["llm_api_key"] = req.llm_api_key
    session["llm_send_raw"] = bool(req.llm_send_raw)
    session["llm_mode"] = req.llm_mode
    # save snapshot intentionally excludes API key
    save_session_snapshot(session)
    return {
        "ok": True,
        "session_id": session_id,
        "llm_enabled": session["llm_enabled"],
        "llm_provider": session["llm_provider"],
        "llm_model": session["llm_model"],
        "llm_send_raw": session["llm_send_raw"],
        "llm_mode": session["llm_mode"],
        "api_key_stored": "memory_only",
    }


@app.get("/api/history")
def list_history() -> dict[str, Any]:
    return {"items": list_session_snapshots(limit=100)}


@app.get("/api/history/{session_id}")
def history_detail(session_id: str) -> dict[str, Any]:
    data = load_session_snapshot(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="history not found")
    return {"snapshot": data}


@app.delete("/api/history/{session_id}")
def delete_history(session_id: str) -> dict[str, Any]:
    if session_id in SESSIONS:
        del SESSIONS[session_id]
    deleted = delete_session_snapshot(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="history not found")
    return {"ok": True, "session_id": session_id}


@app.patch("/api/history/{session_id}/label")
def rename_history(session_id: str, req: RenameRequest) -> dict[str, Any]:
    label = (req.session_label or "").strip()[:80]
    if not label:
        raise HTTPException(status_code=400, detail="session_label 不能为空")

    if session_id in SESSIONS:
        SESSIONS[session_id]["session_label"] = label
        save_session_snapshot(SESSIONS[session_id])

    ok = rename_session_snapshot(session_id, label)
    if not ok and session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="history not found")
    return {"ok": True, "session_id": session_id, "session_label": label}


@app.get("/api/history/{session_id}/export")
def export_history(session_id: str) -> FileResponse:
    out = export_session_snapshot(session_id)
    if not out:
        raise HTTPException(status_code=404, detail="history not found")
    return FileResponse(path=out, filename=out.name, media_type="application/json")


@app.post("/api/history/import", response_model=ImportHistoryResponse)
async def import_history(file: UploadFile = File(...)) -> ImportHistoryResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="导入文件为空")
    try:
        payload = json.loads(content.decode("utf-8", "ignore"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"导入文件不是有效JSON: {exc}") from exc
    old_id = str(payload.get("id", "unknown"))
    new_id = str(uuid.uuid4())
    import_session_snapshot(payload, new_id)
    return ImportHistoryResponse(session_id=new_id, restored_from=old_id)


@app.post("/api/history/{session_id}/restore")
def restore_history(session_id: str) -> dict[str, Any]:
    data = load_session_snapshot(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="history not found")

    new_id = str(uuid.uuid4())
    bank = _bank_to_items(data.get("bank", []))
    restored = {
        "id": new_id,
        "company": data.get("company", ""),
        "role": data.get("role", ""),
        "resume_text": data.get("resume_text", ""),
        "bank": bank,
        "cursor": int(data.get("cursor", 0)),
        "round_limit": int(data.get("round_limit", 14)),
        "target_minutes": int(data.get("target_minutes", 35)),
        "mode": data.get("mode", "mixed"),
        "pressure_level": data.get("pressure_level", "standard"),
        "interviewer_style": data.get("interviewer_style", "professional"),
        "session_label": data.get("session_label", "面试练习会话"),
        "llm_enabled": False,
        "llm_provider": "openai_compatible",
        "llm_model": "gpt-4o-mini",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_api_key": "",
        "llm_send_raw": False,
        "llm_mode": "assist_only",
        "history": data.get("history", []),
        "dialog": data.get("dialog", []),
        "materials": data.get("materials", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    SESSIONS[new_id] = restored
    current = _pick_question(restored)
    save_session_snapshot(restored)
    return {
        "session_id": new_id,
        "mode": restored["mode"],
        "target_minutes": restored["target_minutes"],
        "round_limit": restored["round_limit"],
        "suggested_rounds": restored["round_limit"],
        "pressure_level": restored["pressure_level"],
        "interviewer_style": restored["interviewer_style"],
        "session_label": restored["session_label"],
        "llm_enabled": False,
        "llm_provider": restored["llm_provider"],
        "llm_model": restored["llm_model"],
        "llm_mode": restored["llm_mode"],
        "question": asdict(current) if current else None,
        "total_candidates": len(bank),
        "dialog": restored["dialog"],
        "restored_from": session_id,
    }


@app.post("/api/session/{session_id}/answer")
async def submit_answer(session_id: str, req: AnswerRequest) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    if _effective_round_count(session) >= session["round_limit"]:
        return {"done": True, "message": "本轮面试已结束，请进入复盘"}

    q = _pick_question(session)
    if not q:
        return {"done": True, "message": "题目已全部完成"}

    evaluation = score_answer(q, req.answer, pressure_level=session.get("pressure_level", "standard"))
    interrupt = detect_interruption(
        q,
        req.answer,
        evaluation,
        pressure_level=session.get("pressure_level", "standard"),
    )
    interviewer_reply = build_interviewer_reply(
        q,
        req.answer,
        evaluation,
        pressure_level=session.get("pressure_level", "standard"),
        interviewer_style=session.get("interviewer_style", "professional"),
        turn_index=len(session["history"]),
    )
    llm_used = False
    llm_error = ""
    llm_mode = session.get("llm_mode", "assist_only")
    local_reply = interviewer_reply

    ans_text = req.answer.strip()
    weak_retry = (not ans_text) or (len(ans_text) <= 6) or (
        evaluation.get("score", 0) < 3 and interrupt["interrupted"]
    )

    if weak_retry:
        retry_state = session.setdefault("retry_state", {})
        key = str(session.get("cursor", 0))
        retry_state[key] = int(retry_state.get(key, 0)) + 1
        retry_count = retry_state[key]
        session["dialog"].append({"role": "candidate", "text": req.answer})
        if interrupt["interrupted"]:
            session["dialog"].append({"role": "interviewer_interrupt", "text": interrupt["message"]})
        coaching = "请直接覆盖这题的关键子问，不要只给编号。"
        if "MPI" in q.question or "mpi" in q.question.lower():
            coaching = "重答要求：必须包含“进程vs线程差异 + 2个通信原语及场景 + 1组加速比数据”。"
        elif "Ghost" in q.question or "ghost" in q.question.lower():
            coaching = "重答要求：必须包含“通信时序 + 死锁/错位排障 + 量化收益”。"
        elif "DEM" in q.question or "离散元" in q.question:
            coaching = "重答要求：必须包含“接触模型 + 时间步约束 + 邻域搜索复杂度优化”。"
        session["dialog"].append({"role": "interviewer", "text": interviewer_reply})
        session["dialog"].append({"role": "interviewer", "text": coaching})
        session["dialog"].append(
            {
                "role": "interviewer",
                "text": f"继续当前题（第{retry_count}次重答）：{q.question}",
            }
        )
        save_session_snapshot(session)
        return {
            "done": False,
            "evaluation": {
                "question": q.question,
                "category": q.category,
                "answer": req.answer,
                **evaluation,
                "interrupted": interrupt["interrupted"],
                "interruption_message": interrupt["message"],
                "interruption_reasons": interrupt["reasons"],
                "ideal": ideal_answer_template(q.question),
                "interviewer_reply": interviewer_reply,
                "llm_used": False,
                "llm_error": "",
                "repeat_current": True,
            },
            "next_question": asdict(q),
            "dialog": session["dialog"],
        }

    if session.get("llm_enabled") and session.get("llm_api_key"):
        try:
            outbound_answer = req.answer
            if not session.get("llm_send_raw", False):
                outbound_answer = redact_text(outbound_answer)
            if session.get("llm_provider") == "openai_compatible":
                llm_reply = await generate_interviewer_reply_via_openai_compatible(
                    api_key=session.get("llm_api_key", ""),
                    model=session.get("llm_model", "gpt-4o-mini"),
                    question=q.question,
                    answer=outbound_answer,
                    eval_info=evaluation,
                    pressure_level=session.get("pressure_level", "standard"),
                    interviewer_style=session.get("interviewer_style", "professional"),
                    base_url=session.get("llm_base_url", "https://api.openai.com/v1"),
                )
                if llm_reply:
                    ok, reason = _llm_reply_quality_ok(llm_reply)
                    if not ok:
                        llm_error = f"llm_rejected:{reason}"
                    else:
                        llm_used = True
                        if llm_mode == "assist_only":
                            interviewer_reply = f"{local_reply}\n补充：{llm_reply}"
                        else:
                            interviewer_reply = llm_reply
        except Exception as exc:
            llm_error = str(exc)[:200]
    record = {
        "question": q.question,
        "category": q.category,
        "answer": req.answer,
        **evaluation,
        "interrupted": interrupt["interrupted"],
        "interruption_message": interrupt["message"],
        "interruption_reasons": interrupt["reasons"],
        "ideal": ideal_answer_template(q.question),
        "interviewer_reply": interviewer_reply,
        "llm_used": llm_used,
        "llm_error": llm_error,
        "count_for_round": True,
    }
    session["history"].append(record)
    session["dialog"].append({"role": "candidate", "text": req.answer})
    if interrupt["interrupted"]:
        session["dialog"].append({"role": "interviewer_interrupt", "text": interrupt["message"]})
    session["dialog"].append({"role": "interviewer", "text": interviewer_reply})
    session["cursor"] += 1
    if "retry_state" in session:
        session["retry_state"].pop(str(session["cursor"] - 1), None)

    next_q = _pick_question(session)
    done = (next_q is None) or (_effective_round_count(session) >= session["round_limit"])
    if not done and next_q:
        session["dialog"].append({"role": "interviewer", "text": f"下一题：{next_q.question}"})
    save_session_snapshot(session)

    return {
        "done": done,
        "evaluation": record,
        "next_question": asdict(next_q) if not done and next_q else None,
        "dialog": session["dialog"],
    }


@app.get("/api/session/{session_id}/review")
def review_session(session_id: str) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    history = session["history"]
    if not history:
        raise HTTPException(status_code=400, detail="还没有答题记录")

    avg = round(sum(item["score"] for item in history) / len(history), 2)
    avg_tech = round(sum(item["dimensions"]["technical"] for item in history) / len(history), 2)
    avg_struct = round(sum(item["dimensions"]["structure"] for item in history) / len(history), 2)
    avg_comm = round(sum(item["dimensions"]["communication"] for item in history) / len(history), 2)
    avg_fit = round(sum(item["dimensions"]["job_fit"] for item in history) / len(history), 2)
    weak = [h for h in history if h["score"] < 5]
    medium = [h for h in history if 5 <= h["score"] < 8]
    strong = [h for h in history if h["score"] >= 8]
    save_session_snapshot(session)

    return {
        "summary": {
            "total": len(history),
            "average_score": avg,
            "weak_count": len(weak),
            "medium_count": len(medium),
            "strong_count": len(strong),
            "mode": session.get("mode", "mixed"),
            "dimension_avg": {
                "technical": avg_tech,
                "structure": avg_struct,
                "communication": avg_comm,
                "job_fit": avg_fit,
            },
        },
        "weak_points": [
            {
                "question": x["question"],
                "feedback": x["feedback"],
                "ideal": x["ideal"],
                "dimensions": x["dimensions"],
            }
            for x in weak[:8]
        ],
        "system_design_template": {
            "steps": [
                "澄清需求和范围（用户、流量、SLA、隐私合规）",
                "画核心链路（入口->鉴权->业务->存储->审计）",
                "拆数据模型和存储选型（冷热分层、索引）",
                "说明高可用策略（限流、熔断、重试、降级）",
                "给监控指标和故障预案（错误率、延迟、容量）",
            ]
        },
        "all_records": history,
        "dialog": session.get("dialog", []),
        "materials": session.get("materials", []),
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
