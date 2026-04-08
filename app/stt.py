from __future__ import annotations

import os
import tempfile
from pathlib import Path


class STTUnavailableError(RuntimeError):
    pass


_MODEL = None


def _load_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise STTUnavailableError(
            "faster-whisper 未安装。请执行: pip install -r requirements-whisper.txt"
        ) from exc

    model_name = os.environ.get("WHISPER_MODEL", "small")
    device = os.environ.get("WHISPER_DEVICE", "cpu")
    compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
    _MODEL = WhisperModel(model_name, device=device, compute_type=compute_type)
    return _MODEL


def transcribe_audio_bytes(content: bytes, filename: str = "audio.webm", language: str = "zh") -> str:
    if not content:
        return ""

    model = _load_model()
    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as fp:
        fp.write(content)
        fp.flush()
        segments, _ = model.transcribe(
            fp.name,
            beam_size=5,
            vad_filter=True,
            language=language,
        )
        text = "".join(seg.text for seg in segments).strip()
    return text
