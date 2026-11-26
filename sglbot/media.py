"""Image generation, image understanding, and free text-to-video."""

from __future__ import annotations
import os

import base64
import json
import logging
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

GEMINI_IMAGE_MODELS = (
    "gemini-3.1-flash-lite-image",
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
    "gemini-nano-banana-2.1",
)
POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"
NATIVE_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Free-tier Gemini image/video generation reports limit: 0 until billing is on.
_gemini_image_blocked = False
_gemini_lock = threading.Lock()

_IMAGE_INTENT = re.compile(
    r"""(?ix)
    (?:
        (?:আমাকে\s+)?(?:একটা|একটি|কিছু)?\s*(?:ছবি|ইমেজ|পিকচার|photo|image|picture|illustration)
        \s*(?:বানাও|বানান|বানাওতো|তৈরি(?:\s*কর(?:ো|ুন|াও|া))?|আঁক(?:ো|ুন)?|generate|create|make|draw)
      |
        (?:বানাও|বানান|তৈরি(?:\s*কর(?:ো|ুন|া))?|আঁক(?:ো|ুন)?|generate|create|draw|make)
        \s+(?:আমাকে\s+)?(?:একটা|একটি|an?\s+|the\s+)?(?:ছবি|ইমেজ|পিকচার|photo|image|picture|illustration)
      |
        (?:generate|create|draw|make(?:\s+me)?)\s+(?:an?\s+)?(?:image|picture|photo|illustration)(?:\s+of)?
      |
        (?:please\s+)?(?:an?\s+)?(?:image|picture|photo)\s+of\b
    )
    """
)

_VIDEO_INTENT = re.compile(
    r"""(?ix)
    (?:
        (?:আমাকে\s+)?(?:একটা|একটি|কিছু)?\s*(?:ভিডিও|ভিডিও|video|clip)
        \s*(?:বানাও|বানান|তৈরি(?:\s*কর(?:ো|ুন|াও|া))?|generate|create|make)
      |
        (?:বানাও|বানান|তৈরি(?:\s*কর(?:ো|ুন|া))?|generate|create|make)
        \s+(?:আমাকে\s+)?(?:একটা|একটি|an?\s+)?(?:ভিডিও|video|clip)
      |
        (?:generate|create|make(?:\s+me)?)\s+(?:an?\s+)?(?:video|clip)(?:\s+of)?
    )
    """
)

# Trigger phrases stripped to leave the subject as the prompt.
_IMAGE_STRIP = re.compile(
    r"""(?ix)
    ^(?:please\s+|can\s+you\s+|could\s+you\s+|আমাকে\s+|একটা\s+|একটি\s+|কিছু\s+)*
    (?:ছবি|ইমেজ|পিকচার|photo|image|picture|illustration)?
    \s*(?:বানাও|বানান|বানাওতো|তৈরি(?:\s*কর(?:ো|ুন|াও|া))?|আঁক(?:ো|ুন)?|generate|create|draw|make(?:\s+me)?(?:\s+an?)?|of)?
    \s*(?:ছবি|ইমেজ|পিকচার|an?\s+image|an?\s+picture|an?\s+photo|image|picture|photo|illustration)?
    \s*(?:of|for|:|—|-)?\s*
    """
)


@dataclass
class ImageResult:
    data: bytes
    mime: str
    source: str  # "gemini:<model>" or "pollinations"
    filename: str


def looks_like_image_request(text: str) -> bool:
    return bool(_IMAGE_INTENT.search(text or ""))


def looks_like_video_request(text: str) -> bool:
    return bool(_VIDEO_INTENT.search(text or ""))


def extract_image_prompt(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^/image(@\w+)?\s*", "", cleaned, flags=re.I).strip()
    # Peel a leading trigger once.
    cleaned = _IMAGE_STRIP.sub("", cleaned, count=1).strip(" \t.,:;-—")
    # If the remainder still starts with a trigger word, strip again.
    cleaned = _IMAGE_STRIP.sub("", cleaned, count=1).strip(" \t.,:;-—")
    return cleaned


_VIDEO_STRIP = re.compile(
    r"""(?ix)
    ^(?:please\s+|can\s+you\s+|could\s+you\s+|আমাকে\s+|একটা\s+|একটি\s+|কিছু\s+)*
    (?:ভিডিও|video|clip)?
    \s*(?:বানাও|বানান|তৈরি(?:\s*কর(?:ো|ুন|াও|া))?|generate|create|make(?:\s+me)?(?:\s+an?)?|of)?
    \s*(?:ভিডিও|a\s+video|an\s+video|video|clip)?
    \s*(?:of|for|:|—|-)?\s*
    """
)


def extract_video_prompt(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^/video(@\w+)?\s*", "", cleaned, flags=re.I).strip()
    cleaned = _VIDEO_STRIP.sub("", cleaned, count=1).strip(" \t.,:;-—")
    cleaned = _VIDEO_STRIP.sub("", cleaned, count=1).strip(" \t.,:;-—")
    return cleaned


def has_bengali(text: str) -> bool:
    return any("\u0980" <= ch <= "\u09FF" for ch in (text or ""))


def video_coming_soon_message(user_text: str = "") -> str:
    bn = (
        "ভিডিও তৈরি এখনো চালু করা যায়নি — শিগগিরই আসছে।\n"
        "এর জন্য Google AI Studio-তে Gemini API-এর পেইড বিলিং চালু করতে হয়। "
        "এই ফ্রি কীতে ভিডিও কোটা ০। বর্তমান মডেল `gemini-omni-1.2-flash` "
        "(Veo 3.1 প্রিভিউ ২২ অক্টোবর ২০২৬-এ বন্ধ)। পেইড টিয়ারে দাম প্রায় "
        "$0.07 প্রতি সেকেন্ড (৭২০p; ~$0.70 একটি ১০ সেকেন্ডের ক্লিপ)।"
    )
    en = (
        "Video generation isn't available yet — it's coming soon.\n"
        "It needs a paid Gemini API plan (billing enabled in Google AI Studio). "
        "This free-tier key has video quota 0. The current model is "
        "`gemini-omni-1.2-flash` (Veo 3.1 preview shut down 22 Oct 2026). "
        "Paid pricing is about $0.07/sec at 720p (~$0.70 for a 10s clip)."
    )
    if has_bengali(user_text) and not re.search(r"[A-Za-z]{4,}", user_text or ""):
        return bn
    if has_bengali(user_text):
        return f"{bn}\n\n{en}"
    return f"{en}\n\n{bn}"


def _http_json(method: str, url: str, headers: dict, body: dict | None, timeout: int):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": {"message": raw[:500], "code": e.code}}


def _try_gemini_image(api_key: str, prompt: str) -> ImageResult | None:
    global _gemini_image_blocked
    with _gemini_lock:
        if _gemini_image_blocked:
            return None
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    for model in GEMINI_IMAGE_MODELS:
        url = f"{NATIVE_BASE}/{model}:generateContent"
        try:
            status, obj = _http_json(
                "POST", url, {"x-goog-api-key": api_key}, body, timeout=70
            )
        except Exception:
            logger.warning("Gemini image request failed for %s", model, exc_info=True)
            continue
        if status != 200:
            err = (obj.get("error") or {})
            message = str(err.get("message") or "")
            logger.info("Gemini image %s status=%s: %s", model, status, message[:200])
            low = message.lower()
            if status in (429, 403) and ("limit: 0" in low or "free tier" in low or "free_tier" in low):
                with _gemini_lock:
                    _gemini_image_blocked = True
                return None
            continue
        parts = (
            ((obj.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        )
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data") or {}
            data_b64 = inline.get("data")
            if not data_b64:
                continue
            mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
            raw = base64.b64decode(data_b64)
            ext = "png" if "png" in mime else "jpg"
            return ImageResult(raw, mime, f"gemini:{model}", f"nexora.{ext}")
    return None


def _pollinations_image(prompt: str) -> ImageResult:
    import time

    q = urllib.parse.quote(prompt[:800], safe="")
    urls = [
        f"{POLLINATIONS_BASE}{q}?width=1024&height=1024&nologo=true",
        f"{POLLINATIONS_BASE}{q}?width=768&height=768&nologo=true&model=flux",
    ]
    last_error: Exception | None = None
    for attempt in range(4):
        url = urls[attempt % len(urls)]
        req = urllib.request.Request(url, headers={"User-Agent": "NexoraAI/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()
                mime = resp.headers.get("Content-Type") or "image/jpeg"
            if data and (data[:2] in (b"\xff\xd8", b"\x89P") or data[:8] == b"\x89PNG\r\n\x1a\n"):
                ext = "png" if data[:2] == b"\x89P" else "jpg"
                mime = "image/png" if ext == "png" else "image/jpeg"
                return ImageResult(data, mime, "pollinations", f"nexora.{ext}")
            last_error = RuntimeError("Pollinations did not return an image")
        except Exception as exc:
            last_error = exc
            logger.warning("Pollinations attempt %s failed: %s", attempt + 1, type(exc).__name__)
        time.sleep(1.5 * (attempt + 1))
    raise last_error or RuntimeError("Pollinations did not return an image")


def generate_image(api_key: str, prompt: str) -> ImageResult:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("empty prompt")
    if api_key:
        result = _try_gemini_image(api_key, prompt)
        if result:
            return result
        logger.info("Gemini image generation unavailable; using Pollinations fallback")
    # Pollinations (honours its rate-limit Retry-After, never keeps the "free limit" placeholder),
    # then the free FLUX.1-schnell Hugging Face Space.
    from sglbot import photoedit

    from sglbot import design

    # Text posts (hooks, quotes, offers...) get real typography over an AI background; pictures get a
    # faithful English prompt (free generators garble text and understand English far better than Bengali).
    plan = design.plan(api_key, os.getenv("AI_MODEL") or "gemini-3.5-flash-lite", prompt)
    if plan["type"] == "design":
        bg = photoedit.generate_image_free(plan["bg_prompt"], 832, 1024)
        png = design.render(plan, bg[0] if bg else None)
        return ImageResult(png, "image/png", "design", "nexora-post.png")
    prompt = plan.get("prompt") or prompt
    got = photoedit.generate_image_free(prompt, 1024, 1024)
    if got:
        data, source = got
        return ImageResult(data, "image/jpeg", source, "nexora.jpg")
    raise RuntimeError("all free image generators are busy")


def understand_image(
    api_key: str,
    model: str,
    image_bytes: bytes,
    mime: str,
    question: str,
) -> str:
    if not api_key:
        raise RuntimeError("missing Gemini API key")
    mime = mime or "image/jpeg"
    if mime not in ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"):
        mime = "image/jpeg"
    question = (question or "").strip() or (
        "Describe this image clearly. If there is visible text, transcribe it. "
        "Reply in the same language as this request if specified; otherwise use "
        "the language of any visible text, or English."
    )
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": question},
                    {
                        "inline_data": {
                            "mime_type": mime,
                            "data": base64.b64encode(image_bytes).decode(),
                        }
                    },
                ],
            }
        ]
    }
    url = f"{NATIVE_BASE}/{model}:generateContent"
    status, obj = _http_json(
        "POST", url, {"x-goog-api-key": api_key}, body, timeout=70
    )
    if status != 200:
        err = obj.get("error") or {}
        raise RuntimeError(err.get("message") or f"vision HTTP {status}")
    parts = ((obj.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = "\n".join((p.get("text") or "").strip() for p in parts if p.get("text")).strip()
    if not text:
        raise RuntimeError("empty vision reply")
    return text


@dataclass
class VideoResult:
    data: bytes
    mime: str
    source: str
    filename: str


# Official Lightricks public Space, LTX-Video 0.9.8 distilled.
# License (LTXV Open Weights 0.X) allows commercial/SaaS use for entities
# under $10M annual revenue, subject to Attachment A use restrictions.
# Unauthenticated ZeroGPU quota is about 2 minutes/day.
LTX_SPACE = "Lightricks/ltx-video-distilled"
VIDEO_TIMEOUT_SECONDS = 180
DEFAULT_VIDEO_DURATION = 2.0


def video_wait_message(user_text: str = "") -> str:
    bn = "ছোট একটি ভিডিও বানাচ্ছি, এক-দুই মিনিট লাগতে পারে। অনুগ্রহ করে অপেক্ষা করুন।"
    en = "I'm making a short video — this can take a minute or two. Please wait."
    if has_bengali(user_text) and not re.search(r"[A-Za-z]{4,}", user_text or ""):
        return bn
    if has_bengali(user_text):
        return f"{bn}\n{en}"
    return f"{en}\n{bn}"


def video_fail_message(user_text: str = "") -> str:
    bn = (
        "দুঃখিত, এই মুহূর্তে ভিডিও তৈরি করা যায়নি। "
        "ফ্রি কিউ ব্যস্ত থাকতে পারে — একটু পরে আবার চেষ্টা করুন। "
        "ছোট ২ সেকেন্ডের ক্লিপ বানাতে /video দিয়ে বিষয়টা লিখুন।"
    )
    en = (
        "Sorry, I couldn't create a video just now. "
        "The free queue may be busy — please try again in a little while. "
        "Use /video plus a short description for a ~2 second clip."
    )
    if has_bengali(user_text) and not re.search(r"[A-Za-z]{4,}", user_text or ""):
        return bn
    if has_bengali(user_text):
        return f"{bn}\n\n{en}"
    return f"{en}\n\n{bn}"


def video_prompt_needed_message() -> str:
    return (
        "কীসের ভিডিও চাই, একটু বলে দিন। উদাহরণ: /video a red apple spinning  "
        "অথবা  ভিডিও বানাও একটি লাল আপেল ঘুরছে।\n"
        "Tell me what to film. Example: /video a red apple spinning  "
        "or  ভিডিও বানাও একটি লাল আপেল ঘুরছে।"
    )


def generate_video(prompt: str, duration: float = DEFAULT_VIDEO_DURATION) -> VideoResult:
    """Generate a short MP4 via the official LTX-Video Hugging Face Space (free, no key)."""
    from pathlib import Path

    from gradio_client import Client

    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("empty prompt")
    duration = min(max(float(duration), 1.0), 4.0)

    import os

    hf_token = (os.getenv("HF_TOKEN") or "").strip() or None
    client = Client(LTX_SPACE, token=hf_token) if hf_token else Client(LTX_SPACE)
    result = client.predict(
        prompt=prompt,
        negative_prompt="worst quality, inconsistent motion, blurry, jittery, distorted",
        input_image_filepath=None,
        input_video_filepath=None,
        height_ui=512,
        width_ui=704,
        mode="text-to-video",
        duration_ui=duration,
        ui_frames_to_use=9,
        seed_ui=0,
        randomize_seed=True,
        ui_guidance_scale=1,
        improve_texture_flag=False,
        api_name="/text_to_video",
    )
    video = result[0] if isinstance(result, (list, tuple)) else result
    path = video.get("video") if isinstance(video, dict) else video
    if not path:
        raise RuntimeError("LTX Space returned no video path")
    src = Path(path)
    if not src.exists():
        raise RuntimeError("LTX Space video file is missing")
    data = src.read_bytes()
    if b"ftyp" not in data[:16]:
        raise RuntimeError("LTX Space did not return an MP4")
    return VideoResult(data, "video/mp4", f"hf-space:{LTX_SPACE}", "nexora.mp4")
