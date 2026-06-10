"""Stage A: ASR 提取 — 用 faster-whisper 从视频中提取口语旁白。"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from .schemas import ASRSegment

logger = logging.getLogger(__name__)

# 模型大小: small 平衡速度和质量, medium 更准但慢一倍
ASR_MODEL_SIZE = os.environ.get("ASR_MODEL_SIZE", "small")


def _extract_audio(video_path: str) -> str:
    """从视频提取音频为 WAV。"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", tmp_path],
        capture_output=True, timeout=60,
    )
    return tmp_path


def extract_asr(video_path: str) -> list[ASRSegment]:
    """从视频中提取 ASR 文本。

    返回按时间排序的 ASRSegment 列表。
    如果 faster-whisper 不可用或出错，返回空列表。
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning("faster-whisper 未安装, 跳过 ASR")
        return []

    audio_path = None
    try:
        audio_path = _extract_audio(video_path)
        if not Path(audio_path).is_file():
            logger.warning("音频提取失败")
            return []

        # CPU 模式 (MPS 不被 ctranslate2 直接支持, 回退 CPU)
        model = WhisperModel(ASR_MODEL_SIZE, device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            audio_path,
            language="zh",
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )

        results = []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            results.append(ASRSegment(
                start=round(seg.start, 2),
                end=round(seg.end, 2),
                text=text,
                no_speech_prob=round(seg.no_speech_prob, 3),
            ))

        logger.info(f"ASR 提取 {len(results)} 段, 语言={info.language}, 概率={info.language_probability:.2f}")
        return results

    except Exception as e:
        logger.warning(f"ASR 提取失败: {e}")
        return []
    finally:
        if audio_path:
            Path(audio_path).unlink(missing_ok=True)
