from __future__ import annotations

import json
from typing import Any

import httpx


def _build_prompt(question: str, answer: str, eval_info: dict[str, Any], pressure: str, style: str) -> str:
    return (
        "你是中文技术面试官助理。请基于候选人的回答，输出“1句补充反馈+1个追问问题”。"
        "\n要求：仅作为补充，不要改写主结论；不要输出JSON；总长度控制在120字以内。"
        f"\n面试官风格: {style}"
        f"\n追问强度: {pressure}"
        f"\n问题: {question}"
        f"\n候选人回答: {answer}"
        f"\n本地评估: score={eval_info.get('score')} level={eval_info.get('level')} dims={eval_info.get('dimensions')}"
        "\n请输出：补充反馈。追问：xxx？"
    )


async def generate_interviewer_reply_via_openai_compatible(
    *,
    api_key: str,
    model: str,
    question: str,
    answer: str,
    eval_info: dict[str, Any],
    pressure_level: str,
    interviewer_style: str,
    base_url: str = "https://api.openai.com/v1",
    timeout_sec: float = 20.0,
) -> str:
    prompt = _build_prompt(question, answer, eval_info, pressure_level, interviewer_style)
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是专业面试官。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }

    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"LLM API error: {resp.status_code} {resp.text[:200]}")
        data = resp.json()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise RuntimeError(f"LLM response parse failed: {json.dumps(data)[:200]}") from exc
