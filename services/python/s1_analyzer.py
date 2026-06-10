"""S1 Sample Understanding: video → shots + captions + audio + motion."""

import logging
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass, field

import cv2
import numpy as np
import librosa
from scenedetect import open_video, SceneManager
from scenedetect.detectors import AdaptiveDetector

from motion_analyzer import MotionTimeline

logger = logging.getLogger(__name__)

# Scene detection parameters
SHOT_ADAPTIVE_THRESHOLD = 3.0   # 分数比值阈值；越大越不敏感、切得越少
SHOT_MIN_SCENE_LEN = 15         # 单位：帧；两次切镜之间的最小间隔


@dataclass
class Shot:
    index: int
    start_time: float
    end_time: float
    duration: float
    caption: str = ""
    caption_source: str = ""      # "mimo" / "opencv_fallback"
    clip_path: str = ""
    thumbnail_path: str = ""


@dataclass
class AudioFeatures:
    bpm: float
    energy_curve: list[float] = field(default_factory=list)
    avg_energy: float = 0.0
    rms_mean: float = 0.0
    has_audio: bool = True


@dataclass
class S1Output:
    video_path: str
    total_duration: float
    fps: float
    width: int
    height: int
    shots: list[Shot]
    audio: AudioFeatures
    motion: MotionTimeline | None = None


def detect_shots(video_path: str) -> list[Shot]:
    """Split video into shots using PySceneDetect AdaptiveDetector."""
    video = open_video(video_path)
    scene_manager = SceneManager()
    scene_manager.add_detector(AdaptiveDetector(
        adaptive_threshold=SHOT_ADAPTIVE_THRESHOLD,
        min_scene_len=SHOT_MIN_SCENE_LEN,
    ))
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()

    shots = []
    for i, (start, end) in enumerate(scene_list):
        shots.append(Shot(
            index=i,
            start_time=start.get_seconds(),
            end_time=end.get_seconds(),
            duration=end.get_seconds() - start.get_seconds(),
        ))

    # If no scenes detected, treat entire video as one shot
    if not shots:
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        total_dur = total_frames / fps
        shots.append(Shot(index=0, start_time=0.0, end_time=total_dur, duration=total_dur))

    return shots


def extract_middle_frame(video_path: str, time_sec: float):
    """Extract a single frame at the given timestamp. Returns None on failure."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(time_sec * fps))
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None or frame.size == 0:
        return None
    return frame


def extract_multi_frames(video_path: str, start_t: float, end_t: float, n: int = 3) -> list[np.ndarray]:
    """Extract frames from [start_t, end_t].

    For n>=3: first frame + middle frames + last frame (captures text at shot boundaries).
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = []
    if n <= 1:
        t = (start_t + end_t) / 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)
    else:
        # First frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_t * fps))
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)
        # Middle frames
        for i in range(1, n - 1):
            t = start_t + (end_t - start_t) * i / (n - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ret, frame = cap.read()
            if ret and frame is not None:
                frames.append(frame)
        # Last frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(end_t * fps) - 1)
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)
    cap.release()
    return frames


def caption_shot(frames: list[np.ndarray], shot_index: int) -> tuple[str, str]:
    """Generate a motion-aware caption for a shot using multiple frames.

    Args:
        frames: 1-3 frames from the shot (equally spaced in time).
        shot_index: for logging.

    Returns (caption, source) where source is "mimo" / "opencv_fallback".
    """
    import os
    import base64

    if not frames:
        return "", "skipped"

    # Resize frames to max 540px wide (reduce payload for faster VLM response)
    image_contents = []
    for frame in frames:
        h, w = frame.shape[:2]
        if w > 540:
            scale = 540 / w
            frame = cv2.resize(frame, (540, int(h * scale)))
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
        b64 = base64.b64encode(buf).decode("utf-8")
        image_contents.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    # Combined prompt: text transcription + motion + visual language
    if len(frames) >= 2:
        prompt_text = (
            f"以下是同一段动画的 {len(frames)} 帧（第1帧=起始，最后帧=结束）。\n"
            "请按以下格式逐项回答：\n"
            "【屏幕文字】逐字抄录所有屏幕文字（英文/中文/数字），保持原样不省略\n"
            "【运动变化】描述视觉元素的运动（出现/移动/缩放/消失），30-50字\n"
            "【布局】文字和元素的排列方式（横排/竖排/斜排/对角线/居中），主要元素位置\n"
            "【色彩】背景色、主文字色、强调色（尽量用十六进制色号）\n"
            "【排版】字号对比（大/中/小）、字重（粗体/细体）、是否有旋转角度\n"
            "【风格】设计风格一个词（极简/赛博/复古/商务/学术/潮流/其他）"
        )
    else:
        prompt_text = (
            "请按以下格式分析画面：\n"
            "【屏幕文字】逐字抄录所有可见的英文和中文文字，保持原始大小写\n"
            "【布局】文字排列方式和元素位置\n"
            "【色彩】背景色、文字色（十六进制色号）\n"
            "【排版】字号大小、字重\n"
            "【风格】设计风格一个词"
        )

    # Try MiMo VL API (with retry)
    mimo_key = os.environ.get("MIMO_API_KEY", "")
    mimo_url = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1/chat/completions")
    if mimo_key:
        import httpx
        import time as _time
        content = image_contents + [{"type": "text", "text": prompt_text}]
        payload = {
            "model": os.environ.get("MIMO_VLM_MODEL", "mimo-v2.5"),
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 800,
        }
        headers = {"Authorization": f"Bearer {mimo_key}"}
        for attempt in range(3):
            try:
                resp = httpx.post(mimo_url, json=payload, headers=headers, timeout=120.0)
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    result = msg.get("content", "").strip()
                    if not result:
                        result = msg.get("reasoning_content", "").strip()
                    # Filter out thinking traces (MiMo leaks reasoning into content)
                    if result:
                        lines = [l.strip() for l in result.split("\n") if l.strip()]
                        # Skip lines that indicate internal reasoning
                        skip_prefixes = [
                            "用户现在需要", "用户希望我", "用户想要",
                            "直接提供描述", "最终润色", "构建回复",
                            "现在控制字数", "现在检查", "字数约",
                            "这很合适", "好的，", "让我来",
                        ]
                        clean = [l for l in lines
                                 if not any(l.startswith(p) for p in skip_prefixes)]
                        if clean:
                            result = "\n".join(clean)
                        return result, "mimo"
                elif resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning("caption_shot: rate limited (shot %d), retry in %ds", shot_index, wait)
                    _time.sleep(wait)
                    continue
                else:
                    logger.warning("caption_shot: HTTP %d (shot %d)", resp.status_code, shot_index)
                    break
            except httpx.TimeoutException:
                wait = 2 ** (attempt + 1)
                logger.warning("caption_shot: timeout (shot %d, attempt %d), retry in %ds", shot_index, attempt + 1, wait)
                _time.sleep(wait)
            except Exception as e:
                logger.warning("caption_shot: MiMo tier 失败 (shot %d): %s", shot_index, e)
                break

    # Fallback: basic OpenCV analysis on first frame
    h, w = frames[0].shape[:2]
    gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    return f"镜头{shot_index + 1}: {w}x{h}画面, 亮度{'偏亮' if brightness > 128 else '偏暗'}", "opencv_fallback"


def analyze_audio(video_path: str) -> AudioFeatures:
    """Extract audio features using librosa."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
             "-ar", "22050", "-ac", "1", tmp_path],
            capture_output=True, timeout=30,
        )
        if proc.returncode != 0 or not Path(tmp_path).exists() or Path(tmp_path).stat().st_size == 0:
            logger.warning("analyze_audio: ffmpeg 无输出（可能无音轨）")
            return AudioFeatures(bpm=0.0, has_audio=False)

        y, sr = librosa.load(tmp_path, sr=22050)
        if y.size == 0:
            return AudioFeatures(bpm=0.0, has_audio=False)

        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        rms = librosa.feature.rms(y=y)[0]

        n_segments = min(10, len(rms))
        if n_segments > 0:
            segment_size = len(rms) // n_segments
            energy_curve = [
                float(np.mean(rms[i * segment_size:(i + 1) * segment_size]))
                for i in range(n_segments)
            ]
        else:
            energy_curve = []

        bpm = float(tempo) if np.isscalar(tempo) else float(np.atleast_1d(tempo)[0])
        return AudioFeatures(
            bpm=bpm,
            energy_curve=energy_curve,
            avg_energy=float(np.mean(rms)),
            rms_mean=float(np.mean(rms)),
        )
    except Exception as e:
        logger.warning("analyze_audio 失败: %s", e)
        return AudioFeatures(bpm=0.0, has_audio=False)
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def get_video_info(video_path: str) -> dict:
    """Get basic video info via OpenCV."""
    cap = cv2.VideoCapture(video_path)
    info = {
        "fps": cap.get(cv2.CAP_PROP_FPS) or 30.0,
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    info["duration"] = info["total_frames"] / info["fps"]
    cap.release()
    return info


def save_shot_clip(video_path: str, shot: Shot, output_dir: str) -> str:
    """Extract shot as a separate video clip."""
    clip_path = str(Path(output_dir) / f"shot_{shot.index:03d}.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path,
             "-ss", str(shot.start_time),
             "-t", str(shot.duration),
             "-c:v", "libx264", "-preset", "fast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k",
             "-avoid_negative_ts", "make_zero",
             clip_path],
            capture_output=True, timeout=30,
        )
        if Path(clip_path).is_file():
            return clip_path
    except Exception as e:
        logger.warning("save_shot_clip 失败 (shot %d): %s", shot.index, e)
    return ""


def save_thumbnail(frame: np.ndarray, shot_index: int, output_dir: str) -> str:
    """Save shot middle frame as thumbnail image."""
    thumb_path = str(Path(output_dir) / f"frame_{shot_index:03d}.jpg")
    try:
        cv2.imwrite(thumb_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if Path(thumb_path).is_file():
            return thumb_path
    except Exception as e:
        logger.warning("save_thumbnail 失败 (shot %d): %s", shot_index, e)
    return ""


def run_s1(video_path: str, output_dir: str = "") -> S1Output:
    """Full S1 pipeline: video → shots + captions + audio + motion.

    If output_dir is provided, saves shot clips and thumbnails to disk.
    """
    from concurrent.futures import ThreadPoolExecutor
    from motion_analyzer import MotionAnalyzer

    info = get_video_info(video_path)
    shots = detect_shots(video_path)

    # Create output dirs if needed
    clips_dir, frames_dir = "", ""
    if output_dir:
        clips_dir = str(Path(output_dir) / "shots")
        frames_dir = str(Path(output_dir) / "frames")
        Path(clips_dir).mkdir(parents=True, exist_ok=True)
        Path(frames_dir).mkdir(parents=True, exist_ok=True)

    # Phase 1: extract 3 frames per shot for motion-aware captioning
    shot_frames: dict[int, list[np.ndarray]] = {}
    for shot in shots:
        frames = extract_multi_frames(video_path, shot.start_time, shot.end_time, n=3)
        shot_frames[shot.index] = frames
        if output_dir and frames:
            shot.thumbnail_path = save_thumbnail(frames[0], shot.index, frames_dir)
            shot.clip_path = save_shot_clip(video_path, shot, clips_dir)

    # Phase 2: caption in parallel (I/O-bound — API calls, 3 frames per shot)
    def _caption_one(shot: Shot) -> None:
        frames = shot_frames.get(shot.index, [])
        if not frames:
            shot.caption = ""
            shot.caption_source = "skipped"
            return
        caption, source = caption_shot(frames, shot.index)
        shot.caption = caption
        shot.caption_source = source

    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(_caption_one, shots))

    audio = analyze_audio(video_path)

    # Phase 3: motion analysis (optical flow + element tracking)
    motion = None
    try:
        analyzer = MotionAnalyzer.create(video_path)
        motion = analyzer.analyze(video_path)
        logger.info(
            "run_s1: motion analysis done — %d energy points, %d events, %d tracks",
            len(motion.visual_energy_curve),
            len(motion.motion_events),
            len(motion.tracks),
        )
    except Exception as e:
        logger.warning("run_s1: motion analysis failed: %s", e)

    return S1Output(
        video_path=video_path,
        total_duration=info["duration"],
        fps=info["fps"],
        width=info["width"],
        height=info["height"],
        shots=shots,
        audio=audio,
        motion=motion,
    )
