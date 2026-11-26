"""Free photo editing for Nexora AI.

* Background removal: free Hugging Face Spaces (BiRefNet / BRIA RMBG) through gradio_client,
  falling back to a local `rembg` model when it is installed (the Telegram bot box).
* Background replacement: cutout + a newly generated background (Pollinations, then the free
  FLUX.1-schnell Space), composited with Pillow — or in the browser when running on Vercel.
* Instruction edits ("make it night", "add sunglasses"): free FLUX.1-Kontext / Qwen-Image-Edit
  Spaces. These share a small daily ZeroGPU quota, so failures are reported honestly.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from sglbot.media import NATIVE_BASE, POLLINATIONS_BASE, _http_json

logger = logging.getLogger(__name__)

RMBG_SPACES = (
    ("not-lain/background-removal", "/png"),   # BiRefNet, ZeroGPU (per-IP daily quota)
    ("briaai/BRIA-RMBG-2.0", "/image"),         # ZeroGPU
    ("KenjieDec/RemBG", "/inference"),          # rembg on free CPU hardware, no GPU quota
)
FLUX_SPACE = "black-forest-labs/FLUX.1-schnell"
# Qwen-Image-Edit asks for 240 s of GPU, above the anonymous ZeroGPU limit, so only Kontext is used.
EDIT_SPACES = ("black-forest-labs/FLUX.1-Kontext-Dev",)

OPS = ("none", "remove_bg", "replace_bg", "enhance", "edit")

_EDIT_WORDS = re.compile(
    r"(background|backdrop|\bbg\b|ব্যাকগ্রাউন্ড|ব্যাকগ্রাউন্ড|ব্যাক গ্রাউন্ড|পেছন|পিছন|পটভূমি|"
    r"\bedit|এডিট|change|replace|remove|erase|বদল|পরিবর্তন|পাল্টা|সরা|মুছ|"
    r"\badd\b|যোগ কর|বসা|make (it|me|this|the)|turn (it|this|me)|convert|cartoon|anime|"
    r"ঠিক কর|সুন্দর কর|transparent|png|cut ?out|কাট|" + r"\bhd\b|enhance|restore|upscale|sharpen|clear|clarity|visible|quality|fresh|brighten|"
    r"ঝকঝকে|পরিষ্কার|স্পষ্ট|উজ্জ্বল|রিস্টোর|এইচডি|ঝাপসা|পুরোনো|পুরানো|কোয়ালিটি)",
    re.IGNORECASE,
)


ENHANCE_RE = re.compile(
    r"(\bhd\b|enhance|restore|upscale|sharpen|clear(er)?\b|clarity|more visible|high quality|quality|fresh|brighten|4k|"
    r"ঝকঝকে|পরিষ্কার|স্পষ্ট|উজ্জ্বল|রিস্টোর|এইচডি|ঝাপসা|কোয়ালিটি|পুরোনো ছবি|পুরানো ছবি)", re.IGNORECASE)


class EditError(RuntimeError):
    """Raised with a user-facing reason when every free option failed."""


@dataclass
class EditPlan:
    op: str
    background: str = ""   # English description of the new background (replace_bg)
    instruction: str = ""  # English edit instruction (edit)


def looks_like_edit_request(text: str) -> bool:
    return bool(text and _EDIT_WORDS.search(text))


PLAN_PROMPT = """You route photo requests for an assistant. The user attached ONE photo and wrote the message below.
Decide what they want and answer ONLY with JSON: {"op": "...", "background": "...", "instruction": "..."}
op values:
- "remove_bg": remove/erase the background or make it transparent / PNG cutout.
- "replace_bg": change/replace the background with something else (background = short English description of the NEW background, e.g. "sunny tropical beach with blue sea"; if the user did not say what, invent a tasteful one that fits).
- "enhance": improve the SAME photo without changing its content — make it clearer/sharper/HD/high quality, brighter or more visible, restore an old/faded/blurry photo, fix colours, upscale, "make it fresh".
- "edit": any other change to the photo itself (style, objects, colours, lighting, clothes, cartoon...) — instruction = clear English edit instruction.
- "none": the user only asks a question about the photo, wants a description, caption, text extraction, advice, etc. (no change to the picture).
Message: """


def plan_edit(api_key: str, model: str, text: str) -> EditPlan:
    """Let Gemini decide whether a photo message is an edit request (and which kind)."""
    text = (text or "").strip()
    if not text:
        return EditPlan("none")
    if api_key:
        body = {
            "contents": [{"role": "user", "parts": [{"text": PLAN_PROMPT + text[:1500]}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
        }
        for attempt in range(2):
            try:
                status, obj = _http_json(
                    "POST", f"{NATIVE_BASE}/{model}:generateContent",
                    {"x-goog-api-key": api_key}, body, timeout=30,
                )
                if status == 200:
                    parts = ((obj.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                    raw = "".join(p.get("text") or "" for p in parts).strip()
                    data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
                    op = str(data.get("op") or "none").strip()
                    if op in OPS:
                        return EditPlan(
                            op,
                            str(data.get("background") or "").strip()[:400],
                            str(data.get("instruction") or "").strip()[:600],
                        )
                logger.warning("plan_edit HTTP %s", status)
            except Exception as exc:
                logger.warning("plan_edit attempt %s failed: %s", attempt + 1, type(exc).__name__)
            time.sleep(1.0)
    # Keyword fallback when Gemini is unavailable.
    low = text.lower()
    if not looks_like_edit_request(text):
        return EditPlan("none")
    if re.search(r"(remove|erase|transparent|png|cut ?out|সরা|মুছ|কাট)", low) and not re.search(
        r"(to |with |দিয়ে|করে দাও .*ব্যাকগ্রাউন্ড|change|replace|বদল|পরিবর্তন)", low
    ):
        return EditPlan("remove_bg")
    if ENHANCE_RE.search(low) and not re.search(r"(background|backdrop|\bbg\b|ব্যাকগ্রাউন্ড|cartoon|anime)", low):
        return EditPlan("enhance", instruction=text[:600])
    if re.search(r"(background|backdrop|\bbg\b|ব্যাকগ্রাউন্ড|পেছন|পিছন|পটভূমি)", low):
        return EditPlan("replace_bg", background=text[:300])
    return EditPlan("edit", instruction=text[:600])


# ---------------------------------------------------------------- helpers
def _hf_client(space: str):
    from gradio_client import Client

    token = (os.getenv("HF_TOKEN") or "").strip() or None
    return Client(space, token=token, verbose=False) if token else Client(space, verbose=False)


def _tmp_image(data: bytes, suffix: str = ".jpg") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def _read_result(res) -> bytes:
    """Return the bytes of a gradio file result (path, dict, or tuple of them)."""
    if isinstance(res, (list, tuple)):
        for item in reversed(res):
            try:
                return _read_result(item)
            except Exception:
                continue
        raise RuntimeError("no file in result")
    if isinstance(res, dict):
        res = res.get("path") or res.get("url") or res.get("image")
        return _read_result(res)
    if isinstance(res, str) and os.path.exists(res):
        with open(res, "rb") as f:
            return f.read()
    if isinstance(res, str) and res.startswith("http"):
        with urllib.request.urlopen(urllib.request.Request(res, headers={"User-Agent": "NexoraAI/1.0"}), timeout=60) as r:
            return r.read()
    raise RuntimeError("unexpected result")


def _quota_hint(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "quota" in msg or "zerogpu" in msg or "exceeded" in msg


def downscale(data: bytes, max_side: int = 1280, fmt: str = "JPEG") -> bytes:
    from PIL import Image, ImageOps

    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    if fmt == "JPEG":
        im.convert("RGB").save(out, "JPEG", quality=90)
    else:
        im.save(out, fmt)
    return out.getvalue()


def _has_transparency(png: bytes) -> bool:
    from PIL import Image

    lo, _hi = Image.open(io.BytesIO(png)).getchannel("A").getextrema()
    return lo < 128


def _ensure_png_rgba(data: bytes) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGBA")
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


# ---------------------------------------------------------------- background removal
_REMBG_SESSION = None


def remove_background(image: bytes) -> tuple[bytes, str]:
    """Return (transparent PNG bytes, source)."""
    from gradio_client import handle_file

    src = _tmp_image(downscale(image, 1280))
    errors: list[str] = []
    try:
        # Local CPU model first where it is installed (the Telegram bot box): no quota, no queue.
        try:
            from rembg import new_session, remove  # type: ignore

            global _REMBG_SESSION
            if _REMBG_SESSION is None:
                _REMBG_SESSION = new_session(os.getenv("REMBG_MODEL", "isnet-general-use"))
            with open(src, "rb") as f:
                out = remove(f.read(), session=_REMBG_SESSION)
            return _ensure_png_rgba(out), "rembg-local"
        except ImportError:
            pass
        except Exception as exc:
            errors.append(f"rembg: {type(exc).__name__}")
            logger.warning("local rembg failed: %s", exc)
        for space, api in RMBG_SPACES:
            for attempt in range(2):
                try:
                    if space.startswith("KenjieDec"):
                        res = _hf_client(space).predict(handle_file(src), "isnet-general-use", 0, 0, api_name=api)
                        res = res[0]  # RGBA cutout (second item is the mask)
                    else:
                        res = _hf_client(space).predict(handle_file(src), api_name=api)
                    if space.startswith("briaai") and isinstance(res, (list, tuple)) and len(res) == 2:
                        res = res[1]  # the transparent PNG file
                    png = _ensure_png_rgba(_read_result(res))
                    if not _has_transparency(png):
                        raise RuntimeError("result has no transparent background")
                    return png, space
                except Exception as exc:
                    errors.append(f"{space}: {type(exc).__name__}")
                    logger.warning("rmbg %s attempt %s failed: %s", space, attempt + 1, str(exc)[:200])
                    if _quota_hint(exc):
                        break
                    time.sleep(2)
    finally:
        try:
            os.unlink(src)
        except OSError:
            pass
    raise EditError("background removal unavailable: " + "; ".join(errors))


# ---------------------------------------------------------------- background generation
def pollinations_url(prompt: str, width: int, height: int, seed: int | None = None) -> str:
    import random

    q = urllib.parse.quote(prompt[:700], safe="")
    seed = seed if seed is not None else random.randint(1, 2_000_000_000)
    return f"{POLLINATIONS_BASE}{q}?width={width}&height={height}&nologo=true&seed={seed}"


# Pollinations' rate-limit placeholder pictures ("Busy right now" / "Free limit reached").
PLACEHOLDER_SHA256 = {
    "116b73d9224bb6a5a503addf0105616b8efb60996a54acc1e40909c3f2f18ec1",
    "5b0c323c4889eeb9809c928cba3606c897a36fb3a17b0dc6caf225913b72a82d",
}


def is_placeholder(data: bytes) -> bool:
    """True for Pollinations' 'busy / free limit' notice images (known hash, or the cream text panel)."""
    import hashlib

    if hashlib.sha256(data).hexdigest() in PLACEHOLDER_SHA256:
        return True
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data)).convert("RGB").resize((64, 64))
        band = [im.getpixel((x, y)) for y in range(48, 64) for x in range(64)]
        cream = sum(1 for r, g, b in band if r > 232 and g > 226 and b > 212 and max(r, g, b) - min(r, g, b) < 30)
        dark = sum(1 for r, g, b in band if r + g + b < 240)
        return cream / len(band) > 0.75 and 0.005 < dark / len(band) < 0.2
    except Exception:
        return False


IMAGE_PROMPT_RULES = """You write prompts for a free text-to-image model (FLUX). Turn the user's request into ONE English prompt.
Rules:
- Keep the user's actual subject, objects, people, colours, style, setting and mood exactly; do not add unrelated subjects.
- Use the recent conversation ONLY to resolve references like "it", "this", "same", "এটা", "ওটার", or when the user says
  "make an image for that post" (then depict that post's topic). Ignore older, unrelated topics.
- Make it specific and visual: subject first, then setting, composition/camera, lighting, colours, style.
  For social-media posts/ads: clean modern composition with empty space for text, eye-catching, professional.
- Text in the image: free image models cannot write Bengali/non-Latin script. If the user wants Bengali text, do NOT
  ask for it; ask for clean empty space instead. When the user wants English words shown (a logo's brand name,
  a poster title), include them exactly in double quotes, e.g. text "SocialGrowthLab" (max 5 words).
  Otherwise add "no text, no watermark".
- Avoid: extra fingers, distorted faces, blurry, low quality (say "sharp, high detail, well-proportioned").
- Under 90 words. Reply with the prompt only, no quotes, no explanation."""


def english_image_prompt(api_key: str, model: str, text: str, context: list[dict] | None = None) -> str:
    """Rewrite an image request (any language, maybe referring to the chat) into a strong English FLUX prompt."""
    text = (text or "").strip()
    if not text or not api_key:
        return text
    if text.isascii() and len(text) > 220 and not context:
        return text  # already a detailed English prompt (e.g. written by the chat model)
    convo = ""
    for m in (context or [])[-6:]:
        c = str(m.get("content") or "").strip().replace("\n", " ")
        if c:
            convo += f"{'User' if m.get('role') == 'user' else 'Assistant'}: {c[:400]}\n"
    req = (f"Recent conversation:\n{convo}\n" if convo else "") + f"Image request: {text[:1200]}"
    body = {
        "systemInstruction": {"parts": [{"text": IMAGE_PROMPT_RULES}]},
        "contents": [{"role": "user", "parts": [{"text": req}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400},
    }
    for m in dict.fromkeys([model, "gemini-3.5-flash-lite", "gemini-3-flash-preview"]):
        try:
            status, obj = _http_json("POST", f"{NATIVE_BASE}/{m}:generateContent", {"x-goog-api-key": api_key},
                                     body, timeout=15)
            if status == 200:
                parts = ((obj.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                out = "".join(p.get("text") or "" for p in parts if not p.get("thought")).strip().strip('"')
                if out:
                    return out[:900]
            logger.warning("english_image_prompt %s HTTP %s", m, status)
        except Exception as exc:
            logger.warning("english_image_prompt %s failed: %s", m, type(exc).__name__)
    return text


def _is_image(data: bytes) -> bool:
    return bool(data) and (data[:2] == b"\xff\xd8" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF")


def pollinations_image(prompt: str, width: int = 1024, height: int = 1024, attempts: int = 3,
                       max_wait: float = 20.0) -> bytes | None:
    """Fetch a Pollinations image; on 402/429/503 (rate limit) wait Retry-After and retry.

    Never returns the 'free limit reached' placeholder: those come with a non-200 status.
    """
    for attempt in range(attempts):
        url = pollinations_url(prompt, width, height)
        req = urllib.request.Request(url, headers={"User-Agent": "NexoraAI/1.0", "Accept": "image/jpeg,image/*"})
        wait = 3.0 * (attempt + 1)
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()
            if resp.status == 200 and _is_image(data) and not is_placeholder(data):
                return data
            logger.warning("Pollinations returned a placeholder/non-image (attempt %s)", attempt + 1)
        except urllib.error.HTTPError as exc:
            try:
                wait = float(exc.headers.get("Retry-After") or wait)
            except ValueError:
                pass
            logger.warning("Pollinations HTTP %s (attempt %s)", exc.code, attempt + 1)
        except Exception as exc:
            logger.warning("Pollinations attempt %s failed: %s", attempt + 1, type(exc).__name__)
        if attempt < attempts - 1:
            time.sleep(min(max_wait, max(2.0, wait + 1)))
    return None


def flux_image(prompt: str, width: int = 1024, height: int = 1024) -> bytes | None:
    """Free FLUX.1-schnell Hugging Face Space (ZeroGPU, small daily quota per IP)."""
    scale = min(1.0, 1024 / max(int(width), int(height), 1))
    w = max(256, min(1024, int(width * scale) // 32 * 32))
    h = max(256, min(1024, int(height * scale) // 32 * 32))
    for attempt in range(2):
        try:
            res = _hf_client(FLUX_SPACE).predict(
                prompt=prompt[:700], seed=0, randomize_seed=True, width=w, height=h,
                num_inference_steps=4, api_name="/infer",
            )
            data = _read_result(res[0] if isinstance(res, (list, tuple)) else res)
            if data:
                return downscale(data, 1280)  # webp -> jpeg
        except Exception as exc:
            logger.warning("FLUX space attempt %s failed: %s", attempt + 1, str(exc)[:200])
            if _quota_hint(exc):
                return None
            time.sleep(2)
    return None


def generate_image_free(prompt: str, width: int = 1024, height: int = 1024,
                        use_pollinations: bool = True) -> tuple[bytes, str] | None:
    """FLUX.1-schnell, then Pollinations (with rate-limit retry). Returns (jpeg bytes, source)."""
    # FLUX.1-schnell gives clearly better, more faithful pictures than Pollinations' anonymous model (sana).
    data = flux_image(prompt, width, height)
    if data:
        return data, "flux-schnell"
    if use_pollinations:
        data = pollinations_image(prompt, width, height)
        if data:
            return data, "pollinations"
    return None


# ---------------------------------------------------------------- compositing
def gradient_background(width: int, height: int) -> "Image.Image":  # noqa: F821
    from PIL import Image

    top, bottom = (99, 102, 241), (236, 72, 153)
    grad = Image.new("RGB", (1, 256))
    for y in range(256):
        t = y / 255
        grad.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return grad.resize((width, height))


def composite(cutout_png: bytes, background: bytes | None) -> bytes:
    """Put the subject cutout onto the background (cover-fit). Returns JPEG bytes."""
    from PIL import Image, ImageOps

    fg = Image.open(io.BytesIO(cutout_png)).convert("RGBA")
    w, h = fg.size
    if background:
        bg = Image.open(io.BytesIO(background)).convert("RGB")
        bg = ImageOps.fit(bg, (w, h), method=Image.LANCZOS)
    else:
        bg = gradient_background(w, h)
    bg = bg.convert("RGBA")
    bg.alpha_composite(fg)
    out = io.BytesIO()
    bg.convert("RGB").save(out, "JPEG", quality=92)
    return out.getvalue()


def background_prompt(desc: str) -> str:
    desc = (desc or "beautiful soft studio background").strip()
    return f"{desc}, background scenery only, no people, no person, photorealistic, high detail, natural light"


def replace_background(image: bytes, desc: str, use_pollinations: bool = True) -> tuple[bytes, bytes, str]:
    """Return (composited JPEG, cutout PNG, note)."""
    cutout, src = remove_background(image)
    from PIL import Image

    w, h = Image.open(io.BytesIO(cutout)).size
    scale = 1024 / max(w, h)
    gen = generate_image_free(background_prompt(desc), int(w * scale), int(h * scale), use_pollinations)
    note = f"cutout:{src}"
    if gen:
        note += f", background:{gen[1]}"
        return composite(cutout, gen[0]), cutout, note
    note += ", background:gradient-fallback"
    return composite(cutout, None), cutout, note


# ---------------------------------------------------------------- instruction edits
def instruct_edit(image: bytes, instruction: str) -> tuple[bytes, str]:
    from gradio_client import handle_file

    src = _tmp_image(downscale(image, 1024))
    errors: list[str] = []
    try:
        for space in EDIT_SPACES:
            try:
                client = _hf_client(space)
                if "Kontext" in space:
                    res = client.predict(handle_file(src), instruction[:600], 0, True, 2.5, 20, api_name="/infer")
                else:
                    res = client.predict(handle_file(src), instruction[:600], 0, True, 4.0, 20, False, api_name="/infer")
                data = _read_result(res[0] if isinstance(res, (list, tuple)) else res)
                return downscale(data, 1280), space
            except Exception as exc:
                errors.append(f"{space}: {'quota' if _quota_hint(exc) else type(exc).__name__}")
                logger.warning("edit space %s failed: %s", space, str(exc)[:200])
    finally:
        try:
            os.unlink(src)
        except OSError:
            pass
    raise EditError("; ".join(errors) or "edit failed")


def data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


# ---------------------------------------------------------------- enhance / restore / HD
ENHANCE_SPACES = ("sczhou/CodeFormer", "Nick088/Real-ESRGAN_Pytorch")


def _stretch(im, low_pct: float = 0.6, high_pct: float = 99.4, strength: float = 0.85):
    """Per-channel auto-levels: removes the faded haze and most of the colour cast (white balance)."""
    from PIL import Image

    luts = []
    for ch in im.split():
        hist = ch.histogram(); total = sum(hist) or 1
        acc, lo, hi = 0, 0, 255
        for i, n in enumerate(hist):
            acc += n
            if acc >= total * low_pct / 100:
                lo = i; break
        acc = 0
        for i in range(255, -1, -1):
            acc += hist[i]
            if acc >= total * (100 - high_pct) / 100:
                hi = i; break
        if hi - lo < 30:
            lo, hi = 0, 255
        lut = []
        for v in range(256):
            t = min(255.0, max(0.0, (v - lo) * 255.0 / (hi - lo)))
            lut.append(int(round(v + (t - v) * strength)))
        luts.extend(lut)
    return im.point(luts)


def enhance_local(data: bytes, max_side: int = 2400, upscale: bool = True) -> bytes:
    """Always-available, CPU-only restoration: auto-levels + white balance, gentle gamma, colour, light
    denoise, 2x Lanczos upscale and two-pass unsharp mask. Returns JPEG bytes."""
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    if max(im.size) > 3000:
        im.thumbnail((3000, 3000), Image.LANCZOS)
    im = _stretch(im)
    mean = ImageStat.Stat(im.convert("L")).mean[0] / 255.0
    if mean < 0.42:  # lift a dark/underexposed photo
        g = max(0.65, min(1.0, math_log(0.5) / math_log(max(mean, 0.05))))
        im = im.point([int(255 * ((v / 255.0) ** g)) for v in range(256)] * 3)
    elif mean > 0.68:  # tame a washed-out one
        im = im.point([int(255 * ((v / 255.0) ** 1.15)) for v in range(256)] * 3)
    im = ImageEnhance.Contrast(im).enhance(1.08)
    im = ImageEnhance.Color(im).enhance(1.22)
    im = Image.blend(im, im.filter(ImageFilter.MedianFilter(3)), 0.45)  # light denoise before sharpening
    if upscale:
        f = min(2.0, max_side / max(im.size))
        if f > 1.05:
            im = im.resize((int(im.width * f), int(im.height * f)), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=2.2, percent=95, threshold=3))
    im = im.filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=2))
    out = io.BytesIO(); im.save(out, "JPEG", quality=93, optimize=True)
    return out.getvalue()


def math_log(x: float) -> float:
    import math

    return math.log(x)


def _ai_upscale(data: bytes, deadline: float) -> tuple[bytes, str] | None:
    """Free face/detail restoration Spaces (ZeroGPU; quota per IP). None when busy or out of quota."""
    import tempfile
    from gradio_client import handle_file

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        tf.write(data); path = tf.name
    try:
        for space in ENHANCE_SPACES:
            if time.time() > deadline:
                break
            try:
                c = _hf_client(space)
                if space == "sczhou/CodeFormer":
                    r = c.predict(handle_file(path), True, True, True, 2, 0.7, api_name="/inference")
                    r = r[0] if isinstance(r, (list, tuple)) else r
                else:
                    r = c.predict(handle_file(path), 2, api_name="/predict")
                fp = r.get("path") if isinstance(r, dict) else r
                with open(fp, "rb") as fh:
                    out = fh.read()
                if len(out) > 5000:
                    return out, space
            except Exception as exc:
                logger.warning("enhance space %s failed: %s", space, str(exc)[:160])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    return None


def enhance_photo(data: bytes, try_ai: bool = True, ai_budget: float = 50.0) -> tuple[bytes, str]:
    """Restore/HD a photo. Colours and haze are always fixed locally; detail comes from a free AI
    upscaler when one answers, otherwise from the local 2x upscale + sharpening. Never fails."""
    from PIL import Image

    corrected = enhance_local(data, upscale=False)
    if try_ai:
        got = _ai_upscale(corrected, time.time() + ai_budget)
        if got:
            im = Image.open(io.BytesIO(got[0])).convert("RGB")
            if max(im.size) > 2400:
                im.thumbnail((2400, 2400), Image.LANCZOS)
            out = io.BytesIO(); im.save(out, "JPEG", quality=93, optimize=True)
            return out.getvalue(), got[1]
    return enhance_local(data), "local-enhance"


def before_after(before: bytes, after: bytes, bengali: bool = False) -> bytes:
    """Side-by-side comparison (same height) with small labels."""
    from PIL import Image, ImageDraw, ImageOps

    a = ImageOps.exif_transpose(Image.open(io.BytesIO(before))).convert("RGB")
    b = Image.open(io.BytesIO(after)).convert("RGB")
    h = min(900, max(a.height, 300))
    a = a.resize((max(1, a.width * h // a.height), h), Image.LANCZOS)
    b = b.resize((max(1, b.width * h // b.height), h), Image.LANCZOS)
    gap = 8
    c = Image.new("RGB", (a.width + b.width + gap, h), "white")
    c.paste(a, (0, 0)); c.paste(b, (a.width + gap, 0))
    d = ImageDraw.Draw(c)
    try:
        from sglbot.design import _font
        f = _font("SemiBold", max(18, h // 26))
    except Exception:
        f = None
    for x, label in ((10, "আগে · Before" if bengali else "Before"), (a.width + gap + 10, "পরে · After" if bengali else "After")):
        box = d.textbbox((x + 8, 10), label, font=f)
        d.rounded_rectangle([box[0] - 8, box[1] - 6, box[2] + 8, box[3] + 6], radius=8, fill=(0, 0, 0))
        d.text((x + 8, 10), label, font=f, fill="white")
    out = io.BytesIO(); c.save(out, "JPEG", quality=88)
    return out.getvalue()
