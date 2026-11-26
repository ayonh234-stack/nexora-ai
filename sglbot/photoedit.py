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

OPS = ("none", "remove_bg", "replace_bg", "edit")

_EDIT_WORDS = re.compile(
    r"(background|backdrop|\bbg\b|ব্যাকগ্রাউন্ড|ব্যাকগ্রাউন্ড|ব্যাক গ্রাউন্ড|পেছন|পিছন|পটভূমি|"
    r"\bedit|এডিট|change|replace|remove|erase|বদল|পরিবর্তন|পাল্টা|সরা|মুছ|"
    r"\badd\b|যোগ কর|বসা|make (it|me|this|the)|turn (it|this|me)|convert|cartoon|anime|"
    r"ঠিক কর|সুন্দর কর|transparent|png|cut ?out|কাট)",
    re.IGNORECASE,
)


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
def remove_background(image: bytes) -> tuple[bytes, str]:
    """Return (transparent PNG bytes, source)."""
    from gradio_client import handle_file

    src = _tmp_image(downscale(image, 1280))
    errors: list[str] = []
    try:
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
        # Local model (only where rembg is installed, e.g. the Telegram bot box).
        try:
            from rembg import new_session, remove  # type: ignore

            session = new_session(os.getenv("REMBG_MODEL", "isnet-general-use"))
            with open(src, "rb") as f:
                out = remove(f.read(), session=session)
            return _ensure_png_rgba(out), "rembg-local"
        except ImportError:
            pass
        except Exception as exc:
            errors.append(f"rembg: {type(exc).__name__}")
            logger.warning("local rembg failed: %s", exc)
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
            if resp.status == 200 and _is_image(data):
                return data
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
    """Pollinations (with rate-limit retry) then FLUX.1-schnell. Returns (jpeg bytes, source)."""
    if use_pollinations:
        data = pollinations_image(prompt, width, height)
        if data:
            return data, "pollinations"
    data = flux_image(prompt, width, height)
    if data:
        return data, "flux-schnell"
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
