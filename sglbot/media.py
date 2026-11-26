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



_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_DURATION_WORD = re.compile(
    r"""(?ix)
    (?:^|\s)
    (?:for\s+)?(?:a\s+)?(?:about\s+)?(?:around\s+)?
    (?:10|5|দশ|পাঁচ|পাচ)
    \s*(?:seconds?|secs?|s(?=[\s,.]|$)|সেকেন্ড(?:ের)?)
    (?:\s*(?:long|length))?
    """
)
_DURATION_BARE = re.compile(r"^(?:5|10)\s+")


def parse_video_duration(text: str) -> float | None:
    """Return 5 or 10 if the user named a length, else None."""
    t = (text or "").translate(_BN_DIGITS)
    if re.search(r"(?i)(?:^|\s)(?:দশ|10)\s*(?:s|secs?|seconds?|সেকেন্ড)", t):
        return 10.0
    if re.search(r"(?i)(?:^|\s)(?:পাঁচ|পাচ|5)\s*(?:s|secs?|seconds?|সেকেন্ড)", t):
        return 5.0
    m = re.search(r"(?i)^/video(?:@\w+)?\s+(5|10)\b", t)
    if m:
        return float(m.group(1))
    return None


def resolve_video_duration(text: str = "", explicit: float | None = None, default: float = 10.0) -> float:
    if explicit is not None:
        try:
            return 10.0 if float(explicit) >= 7.5 else 5.0
        except (TypeError, ValueError):
            pass
    parsed = parse_video_duration(text)
    return parsed if parsed is not None else (10.0 if default >= 7.5 else 5.0)


def extract_video_prompt(text: str) -> str:
    cleaned = (text or "").translate(_BN_DIGITS).strip()
    cleaned = re.sub(r"^/video(@\w+)?\s*", "", cleaned, flags=re.I).strip()
    cleaned = _DURATION_BARE.sub("", cleaned)
    cleaned = _DURATION_WORD.sub(" ", cleaned)
    cleaned = _VIDEO_STRIP.sub("", cleaned, count=1).strip(" \t.,:;-—")
    cleaned = _VIDEO_STRIP.sub("", cleaned, count=1).strip(" \t.,:;-—")
    cleaned = _DURATION_WORD.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t.,:;-—")
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
# The Space slider max is 8.5s (257 frames at 30 fps); 10s clips are the
# 8.5s take stretched slightly (~18%) so motion stays real, not a loop.
LTX_SPACE = "Lightricks/ltx-video-distilled"
LTX_SPACE_URL = "https://lightricks-ltx-video-distilled.hf.space"
LTX_MAX_DURATION = 8.5
VIDEO_TIMEOUT_SECONDS = 240
DEFAULT_VIDEO_DURATION = 10.0


def video_wait_message(user_text: str = "") -> str:
    bn = "ভিডিও তৈরি করছি, এক-দুই মিনিট লাগতে পারে। অনুগ্রহ করে অপেক্ষা করুন।"
    en = "I'm creating the video — this can take a minute or two. Please wait."
    if has_bengali(user_text) and not re.search(r"[A-Za-z]{4,}", user_text or ""):
        return bn
    if has_bengali(user_text):
        return f"{bn}\n{en}"
    return f"{en}\n{bn}"


def video_fail_message(user_text: str = "") -> str:
    bn = (
        "দুঃখিত, এই মুহূর্তে ভিডিও তৈরি করা যায়নি। "
        "ফ্রি কিউ ব্যস্ত থাকতে পারে — একটু পরে আবার চেষ্টা করুন। "
        "৫ বা ১০ সেকেন্ডের ভিডিওর জন্য /video দিয়ে বিষয়টা লিখুন।"
    )
    en = (
        "Sorry, I couldn't create a video just now. "
        "The free queue may be busy — please try again in a little while. "
        "Use /video plus a short description for a 5 or 10 second clip."
    )
    if has_bengali(user_text) and not re.search(r"[A-Za-z]{4,}", user_text or ""):
        return bn
    if has_bengali(user_text):
        return f"{bn}\n\n{en}"
    return f"{en}\n\n{bn}"


def video_prompt_needed_message() -> str:
    return (
        "কীসের ভিডিও চাই, একটু বলে দিন। উদাহরণ: /video 10s a red apple spinning  "
        "অথবা  ভিডিও বানাও ১০ সেকেন্ড একটি লাল আপেল ঘুরছে।\n"
        "Tell me what to film. Example: /video 10s a red apple spinning  "
        "or  ভিডিও বানাও ১০ সেকেন্ড একটি লাল আপেল ঘুরছে।"
    )


def video_duration_prompt() -> str:
    return "কত সেকেন্ডের ভিডিও চাই? / How long should the video be?"


def _ffprobe_duration(path: str) -> float | None:
    import shutil
    import subprocess

    probe = shutil.which("ffprobe")
    if not probe:
        return None
    try:
        out = subprocess.check_output(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            timeout=20,
        )
        return float(out.strip())
    except Exception:
        return None


def _scale_mp4_duration(data: bytes, factor: float) -> bytes:
    """Rewrite media timestamps so the same frames play slower/faster (no re-encode)."""
    if factor <= 0 or abs(factor - 1) < 0.01:
        return data
    buf = bytearray(data)

    def boxes(start: int, end: int):
        i = start
        while i + 8 <= end:
            size = int.from_bytes(buf[i : i + 4], "big")
            typ = bytes(buf[i + 4 : i + 8])
            hdr = 8
            if size == 1:
                if i + 16 > end:
                    break
                size = int.from_bytes(buf[i + 8 : i + 16], "big")
                hdr = 16
            elif size == 0:
                size = end - i
            if size < hdr or i + size > end:
                break
            yield i, hdr, size, typ
            i += size

    def u(off: int, n: int) -> int:
        return int.from_bytes(buf[off : off + n], "big")

    def setv(off: int, n: int, value: int) -> None:
        buf[off : off + n] = int(max(0, value)).to_bytes(n, "big")

    def scale_int(off: int, n: int) -> None:
        setv(off, n, round(u(off, n) * factor))

    def walk(start: int, end: int) -> None:
        for i, hdr, size, typ in boxes(start, end):
            body = i + hdr
            if typ in (b"moov", b"trak", b"mdia", b"edts", b"minf", b"stbl"):
                walk(body, i + size)
                continue
            if typ in (b"mvhd", b"mdhd"):
                ver = buf[body]
                if ver == 1:
                    scale_int(body + 4 + 8 + 8 + 4, 8)
                else:
                    scale_int(body + 4 + 4 + 4 + 4, 4)
            elif typ == b"tkhd":
                ver = buf[body]
                if ver == 1:
                    scale_int(body + 4 + 8 + 8 + 4 + 4, 8)
                else:
                    scale_int(body + 4 + 4 + 4 + 4 + 4, 4)
            elif typ == b"elst":
                ver = buf[body]
                count = u(body + 4, 4)
                p = body + 8
                for _ in range(count):
                    if ver == 1:
                        scale_int(p, 8)
                        p += 20
                    else:
                        scale_int(p, 4)
                        p += 12
            elif typ == b"stts":
                count = u(body + 4, 4)
                p = body + 8
                for _ in range(count):
                    scale_int(p + 4, 4)
                    p += 8

    for i, hdr, size, typ in boxes(0, len(buf)):
        if typ == b"moov":
            walk(i + hdr, i + size)
    return bytes(buf)


def stretch_video_bytes(data: bytes, target: float) -> bytes:
    """Stretch or leave an MP4 so its playback length is about `target` seconds."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    target = float(target)
    if not data or b"ftyp" not in data[:16] or target <= 0:
        return data

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.mp4"
        dst = Path(td) / "out.mp4"
        src.write_bytes(data)
        actual = _ffprobe_duration(str(src))
        if actual and actual >= target - 0.15:
            return data
        # Guess 8.5s LTX cap when ffprobe is missing.
        if not actual:
            actual = LTX_MAX_DURATION
        if actual >= target - 0.15:
            return data
        factor = target / actual
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            try:
                # Copy + timestamp scale: same frames, slightly slower motion, no quality loss.
                subprocess.check_call(
                    [ffmpeg, "-y", "-itsscale", f"{factor:.8f}", "-i", str(src),
                     "-c", "copy", "-an", "-movflags", "+faststart", str(dst)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
                )
                out = dst.read_bytes()
                got = _ffprobe_duration(str(dst))
                if out and b"ftyp" in out[:16] and (got is None or got >= target - 0.35):
                    return out
            except Exception:
                logger.warning("ffmpeg itsscale stretch failed, trying Python scale")
        scaled = _scale_mp4_duration(data, factor)
        if scaled and b"ftyp" in scaled[:16]:
            return scaled
        return data


def generate_video(prompt: str, duration: float | None = None) -> VideoResult:
    """Generate an MP4 via the official LTX-Video Hugging Face Space (free, no key).

    The Space itself tops out at 8.5 seconds. A 10 second request generates 8.5s
    and stretches it slightly so the motion stays real (not a loop).
    """
    from pathlib import Path

    from gradio_client import Client

    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("empty prompt")
    duration = resolve_video_duration(prompt, duration)
    ltx_duration = LTX_MAX_DURATION if duration >= 10 else 5.0

    import os

    hf_token = (os.getenv("HF_TOKEN") or "").strip() or None
    client = Client(
        LTX_SPACE,
        token=hf_token,
        verbose=False,
        httpx_kwargs={"timeout": float(VIDEO_TIMEOUT_SECONDS)},
    )
    result = client.predict(
        prompt=prompt,
        negative_prompt="worst quality, inconsistent motion, blurry, jittery, distorted",
        input_image_filepath=None,
        input_video_filepath=None,
        height_ui=512,
        width_ui=704,
        mode="text-to-video",
        duration_ui=ltx_duration,
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
    if duration > ltx_duration + 0.15:
        data = stretch_video_bytes(data, duration)
    return VideoResult(data, "video/mp4", f"hf-space:{LTX_SPACE}", "nexora.mp4")
