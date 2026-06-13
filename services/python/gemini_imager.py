"""Gemini Imagen 3: generate images from text prompts via Google AI API."""

import os
import base64
import random
import time
import httpx
import requests as _requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeout

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def generate_image(
    prompt: str,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    style_profile=None,
    aspect_ratio: str = "",
    reference_image_path: str = "",
) -> str:
    """Generate an image using Gemini Imagen 3 and save to disk.

    Args:
        prompt: text description of the image to generate
        output_path: where to save the generated image
        width/height: image dimensions (default 1080x1920 for vertical video)
        style_profile: optional StyleProfile to inject visual style into prompt
        aspect_ratio: optional aspect ratio hint e.g. "16:9" or "9:16";
            when non-empty, added to generationConfig.imageConfig per Google API spec
        reference_image_path: optional path to a reference image; if the file
            exists it is attached as a style/composition guide with an explicit
            instruction NOT to copy objects, people, text or logos from it.

    Returns:
        path to the saved image, or empty string on failure
    """
    if not GEMINI_API_KEY:
        print("Warning: GEMINI_API_KEY not set, skipping image generation")
        return ""

    # 注入风格上下文（最高杠杆：生成时就把风格喂进去）
    if style_profile:
        prompt = style_profile.to_aigc_prompt(prompt)

    # Use Gemini's best image generation model
    model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={GEMINI_API_KEY}"

    gen_config: dict = {
        "responseModalities": ["TEXT", "IMAGE"],
    }
    if aspect_ratio:
        # Google 官方字段：imageConfig.aspectRatio
        gen_config["imageConfig"] = {"aspectRatio": aspect_ratio}

    # Build parts list — optionally prepend reference image as style guide
    text_instruction = f"Generate an image: {prompt}"
    parts: list[dict] = []

    ref_path = reference_image_path or ""
    if ref_path and os.path.isfile(ref_path):
        try:
            with open(ref_path, "rb") as _rf:
                _ref_bytes = _rf.read()
            _ref_b64 = base64.b64encode(_ref_bytes).decode()
            # Determine mime type from extension
            _ext = os.path.splitext(ref_path)[1].lower()
            _mime = "image/jpeg" if _ext in (".jpg", ".jpeg") else "image/png"
            # Style-guide instruction: do NOT copy content from reference
            style_instruction = (
                "Use the attached image ONLY as a style and composition reference "
                "(color palette, lighting, mood, framing). Generate a completely NEW "
                f"image about: {prompt}. Do NOT copy any objects, people, text or logos "
                "from the reference image."
            )
            parts = [
                {"text": style_instruction},
                {"inlineData": {"mimeType": _mime, "data": _ref_b64}},
            ]
        except Exception as _ref_err:
            print(f"[gemini_imager] Failed to load reference image '{ref_path}': {_ref_err}")
            parts = [{"text": text_instruction}]
    else:
        parts = [{"text": text_instruction}]

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": gen_config,
    }

    MAX_RETRIES = 4
    for attempt in range(MAX_RETRIES):
        try:
            # 用 requests + ThreadPoolExecutor 硬超时（httpx 的 timeout 在 TCP ESTABLISHED 后不生效）
            def _do_request():
                return _requests.post(url, json=payload, timeout=(10, 45))

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_do_request)
                resp = future.result(timeout=60)  # 硬超时 60s

            # 非重试型错误（4xx 除 429）直接返回
            if resp.status_code in (400, 401, 403, 404):
                print(f"Gemini non-retryable error {resp.status_code}: {resp.text[:200]}")
                return ""

            # 429 / 5xx → 重试
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 * (2 ** attempt) + random.uniform(0, 1)
                print(f"Gemini HTTP {resp.status_code}, retry {attempt+1}/{MAX_RETRIES} in {wait:.1f}s")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait)
                    continue
                return ""

            resp.raise_for_status()
            data = resp.json()

            # Extract image from response
            candidates = data.get("candidates", [])
            if not candidates:
                print(f"No candidates in response: {data}")
                return ""

            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    img_data = part["inlineData"]
                    b64 = img_data.get("data", "")

                    if b64:
                        img_bytes = base64.b64decode(b64)
                        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(img_bytes)
                        print(f"Generated image: {output_path} ({len(img_bytes)} bytes)")
                        return output_path

            print(f"No image found in response parts: {[list(p.keys()) for p in parts]}")
            return ""

        except _FuturesTimeout:
            wait = 2 * (2 ** attempt) + random.uniform(0, 1)
            print(f"Gemini image generation hard timeout (60s), retry {attempt+1}/{MAX_RETRIES} in {wait:.1f}s")
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)
            else:
                return ""
        except Exception as e:
            print(f"Gemini image generation failed: {e}")
            return ""

    return ""


def generate_for_gap(prompt: str, phase: str, shot_type: str, output_dir: str) -> str:
    """Generate an image for a specific gap and return the file path.

    Args:
        prompt: the AIGC prompt (from s3_strategist)
        phase: which phase this fills (hook/build/payoff_cta)
        shot_type: what shot type this fills
        output_dir: base output directory

    Returns:
        path to generated image, or empty string
    """
    filename = f"aigc_{phase}_{shot_type}.png"
    output_path = str(Path(output_dir) / filename)
    return generate_image(prompt, output_path)
