"""Video format detection and automatic conversion."""

import subprocess
import tempfile
from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv",
    ".m4v", ".3gp", ".ts", ".mts", ".vob", ".ogv", ".gif",
}

# Formats that OpenCV/PySceneDetect may struggle with → convert first
NEEDS_CONVERSION_CODECS = {
    "vp9", "av1", "hevc", "h265", "prores", "dnxhd", "rawvideo",
}


def probe_video(video_path: str) -> dict:
    """Get video metadata via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", video_path],
            capture_output=True, text=True, timeout=15,
        )
        import json
        return json.loads(result.stdout)
    except Exception:
        return {}


def get_video_codec(probe_data: dict) -> str:
    """Extract video codec name from ffprobe data."""
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream.get("codec_name", "").lower()
    return ""


def needs_conversion(video_path: str) -> bool:
    """Check if video needs format conversion for reliable processing."""
    ext = Path(video_path).suffix.lower()

    # Check extension
    if ext not in SUPPORTED_EXTENSIONS:
        return True

    # Check codec
    probe = probe_video(video_path)
    codec = get_video_codec(probe)
    if codec in NEEDS_CONVERSION_CODECS:
        return True

    # Check if OpenCV can open it
    import cv2
    cap = cv2.VideoCapture(video_path)
    can_read = cap.isOpened()
    ret, frame = cap.read() if can_read else (False, None)
    cap.release()
    if not ret or frame is None:
        return True

    return False


def convert_to_mp4(video_path: str, output_dir: str = "") -> str:
    """Convert video to mp4/h264 for reliable processing.

    Returns path to converted file. If conversion fails, returns original path.
    """
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="vst_convert_")

    output_path = str(Path(output_dir) / (Path(video_path).stem + "_converted.mp4"))

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path,
             "-c:v", "libx264", "-preset", "fast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart",
             "-pix_fmt", "yuv420p",
             output_path],
            capture_output=True, timeout=120,
        )
        if result.returncode == 0 and Path(output_path).is_file():
            return output_path
    except Exception:
        pass

    return video_path


def ensure_compatible(video_path: str) -> str:
    """Ensure video is in a format compatible with the pipeline.

    Returns path to a usable video file (original or converted).
    """
    if not Path(video_path).is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if needs_conversion(video_path):
        return convert_to_mp4(video_path)

    return video_path
