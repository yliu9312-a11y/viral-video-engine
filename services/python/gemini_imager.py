"""Gemini Imagen 3: generate images from text prompts via Google AI API."""

import os
import base64
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
) -> str:
    """Generate an image using Gemini Imagen 3 and save to disk.

    Args:
        prompt: text description of the image to generate
        output_path: where to save the generated image
        width/height: image dimensions (default 1080x1920 for vertical video)
        style_profile: optional StyleProfile to inject visual style into prompt

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

    payload = {
        "contents": [{
            "parts": [{"text": f"Generate an image: {prompt}"}]
        }],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }

    try:
        # 用 requests + ThreadPoolExecutor 硬超时（httpx 的 timeout 在 TCP ESTABLISHED 后不生效）
        def _do_request():
            return _requests.post(url, json=payload, timeout=(10, 45))

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_do_request)
            resp = future.result(timeout=60)  # 硬超时 60s
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
                mime = img_data.get("mimeType", "image/png")
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
        print(f"Gemini image generation hard timeout (60s)")
        return ""
    except Exception as e:
        print(f"Gemini image generation failed: {e}")
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
