"""Text-heavy social graphics (hooks, tips, quotes, offers, carousels) rendered with real typography.

Free image models garble text (and cannot write Bengali at all), so for designs the AI only paints a
text-free background and the exact words are typeset here with Pillow (Hind Siliguri: Bengali + Latin).
"""

from __future__ import annotations

import io
import json
import logging
import os
import re

from sglbot.media import NATIVE_BASE, _http_json

logger = logging.getLogger(__name__)
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

PLAN_PROMPT = """You plan images for an AI assistant. Decide what the user wants and reply with JSON only.

"type":
- "design" when the image must contain readable words: social-media post/graphic with hooks, tips, a list, a quote,
  an offer/sale, an announcement, a poster/flyer/banner/thumbnail with a title, a carousel slide, a greeting card
  with a message, "write ... on the image", "with text", or any request whose value is the text itself.
- "scene" for pictures without required text (photos, art, illustrations, products, people, places, logos without words).

For "scene": {"type":"scene","prompt":"<ONE faithful, vivid English prompt for FLUX, <90 words: subject first, then
setting, composition, lighting, colours, style; keep the user's subject exactly; end with: sharp, high detail,
well-proportioned, no text, no watermark>"}

For "design": {"type":"design",
 "title":"<headline, max 9 words>",
 "subtitle":"<optional short line or empty>",
 "items":["<each list item / hook / tip, max 16 words each, 0-6 items>"],
 "footer":"<ONLY a CTA/@handle/brand the user actually gave (or SocialGrowthLab if it is their own brand's post); otherwise empty. Never invent handles>",
 "size":"portrait" (1080x1350, default for Instagram posts) or "square" (1080x1080),
 "theme":{"bg":"#hex dark or rich colour","text":"#hex high contrast","accent":"#hex"},
 "bg_prompt":"<English prompt for a TEXT-FREE background that fits the topic: soft, uncluttered, abstract or
  blurred scene, room for text, no text, no letters, no watermark>"}
Write title/items/footer in the language the user is using (Bengali stays Bengali, English stays English),
correctly spelled. Use the recent conversation to fill the content when the user refers to it
(e.g. "make an Instagram post of these 3 hooks" -> use those exact hooks). If the user didn't give the text,
write good, specific content yourself. Never invent prices/phone numbers.
"""


def plan(api_key: str, model: str, request: str, context: list[dict] | None = None) -> dict:
    """Return {"type":"scene","prompt":...} or a design spec. Falls back to a scene with the raw request."""
    request = (request or "").strip()
    convo = ""
    for m in (context or [])[-6:]:
        c = str(m.get("content") or "").strip()
        if c:
            convo += f"{'User' if m.get('role') == 'user' else 'Assistant'}: {c[:1200]}\n"
    user = (f"Recent conversation:\n{convo}\n" if convo else "") + f"Image request: {request[:1500]}"
    body = {
        "systemInstruction": {"parts": [{"text": PLAN_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1200, "responseMimeType": "application/json"},
    }
    if api_key:
        for m in dict.fromkeys([model, "gemini-3.5-flash-lite", "gemini-3-flash-preview"]):
            try:
                status, obj = _http_json("POST", f"{NATIVE_BASE}/{m}:generateContent", {"x-goog-api-key": api_key},
                                         body, timeout=20)
                if status != 200:
                    logger.warning("design.plan %s HTTP %s", m, status)
                    continue
                parts = ((obj.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                raw = "".join(p.get("text") or "" for p in parts if not p.get("thought"))
                data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
                return _clean(data, request)
            except Exception as exc:
                logger.warning("design.plan %s failed: %s", m, type(exc).__name__)
    return {"type": "scene", "prompt": request}


def _hex(v: str, default: str) -> str:
    v = str(v or "").strip()
    return v if re.fullmatch(r"#[0-9a-fA-F]{6}", v) else default


def _clean(d: dict, request: str) -> dict:
    if d.get("type") != "design":
        return {"type": "scene", "prompt": str(d.get("prompt") or request)[:900]}
    th = d.get("theme") or {}
    items = [str(x).strip() for x in (d.get("items") or []) if str(x).strip()][:6]
    return {
        "type": "design",
        "title": str(d.get("title") or "").strip()[:120],
        "subtitle": str(d.get("subtitle") or "").strip()[:160],
        "items": [i[:220] for i in items],
        "footer": str(d.get("footer") or "").strip()[:80],
        "size": "square" if d.get("size") == "square" else "portrait",
        "theme": {"bg": _hex(th.get("bg"), "#1e1b4b"), "text": _hex(th.get("text"), "#ffffff"),
                  "accent": _hex(th.get("accent"), "#f59e0b")},
        "bg_prompt": str(d.get("bg_prompt") or "soft abstract gradient background, no text").strip()[:600],
    }


# ---------------------------------------------------------------- rendering
def _font(weight: str, size: int):
    from PIL import ImageFont

    path = os.path.join(FONT_DIR, f"HindSiliguri-{weight}.ttf")
    try:
        return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        return ImageFont.truetype(path, size)


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _wrap(draw, text: str, font, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _layout(draw, spec: dict, W: int, scale: float):
    pad = 96
    inner = W - 2 * pad
    title_f, sub_f = _font("Bold", int(84 * scale)), _font("SemiBold", int(40 * scale))
    item_f, foot_f = _font("SemiBold", int(44 * scale)), _font("Regular", int(32 * scale))
    blocks, h = [], 0
    tl = _wrap(draw, spec["title"], title_f, inner) if spec["title"] else []
    lh_t = int(84 * scale * 1.32)
    blocks.append(("title", tl, title_f, lh_t)); h += len(tl) * lh_t
    if spec["subtitle"]:
        sl = _wrap(draw, spec["subtitle"], sub_f, inner); lh = int(40 * scale * 1.45)
        blocks.append(("subtitle", sl, sub_f, lh)); h += 18 + len(sl) * lh
    h += int(60 * scale)  # accent bar + gap
    num_w = int(74 * scale)
    lh_i = int(44 * scale * 1.42)
    for i, it in enumerate(spec["items"]):
        il = _wrap(draw, it, item_f, inner - num_w - 26)
        blocks.append(("item", il, item_f, lh_i, i + 1)); h += max(len(il) * lh_i, num_w) + int(30 * scale)
    return blocks, h, (foot_f, num_w)


def render(spec: dict, background: bytes | None = None) -> bytes:
    from PIL import Image, ImageDraw, ImageFilter

    W, H = (1080, 1080) if spec.get("size") == "square" else (1080, 1350)
    bg_c, txt_c, acc_c = (_rgb(spec["theme"][k]) for k in ("bg", "text", "accent"))
    canvas = Image.new("RGB", (W, H), bg_c)
    if background:
        try:
            bg = Image.open(io.BytesIO(background)).convert("RGB")
            bg = bg.crop((0, 0, bg.width, int(bg.height * 0.93)))  # drop any generator watermark strip
            s = max(W / bg.width, H / bg.height)
            bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1), Image.LANCZOS)
            bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
            canvas.paste(bg.filter(ImageFilter.GaussianBlur(2)), (0, 0))
        except Exception as exc:
            logger.warning("design background unusable: %s", exc)
    # Tinted overlay so the text is always readable (stronger at the top where the title sits).
    over = Image.new("RGBA", (W, H))
    od = ImageDraw.Draw(over)
    for y in range(H):
        a = int(215 - 70 * (y / H)) if background else 0
        od.line([(0, y), (W, y)], fill=bg_c + (a,))
    if not background:  # soft diagonal gradient from the theme colour
        for y in range(H):
            k = y / H
            od.line([(0, y), (W, y)], fill=tuple(int(c * (1 - 0.35 * k) + a2 * 0.35 * k) for c, a2 in zip(bg_c, acc_c)) + (255,))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), over)
    d = ImageDraw.Draw(canvas)

    pad = 96
    footer_h = 90 if spec.get("footer") else 30
    scale = 1.0
    while True:
        blocks, h, (foot_f, num_w) = _layout(d, spec, W, scale)
        if h <= H - 2 * pad - footer_h or scale < 0.55:
            break
        scale -= 0.05
    y = max(pad, (H - footer_h - h) // 2)
    center = not spec["items"]
    x0, anc = (W // 2, "ma") if center else (pad, "la")
    for b in blocks:
        kind, lines, f, lh = b[0], b[1], b[2], b[3]
        if kind == "title":
            for ln in lines:
                d.text((x0, y), ln, font=f, fill=txt_c, anchor=anc); y += lh
        elif kind == "subtitle":
            y += 18
            for ln in lines:
                d.text((x0, y), ln, font=f, fill=txt_c + (225,), anchor=anc); y += lh
        elif kind == "item":
            n = b[4]
            if n == 1:
                y += 10
            cy = y + 4
            d.ellipse([pad, cy, pad + num_w, cy + num_w], fill=acc_c)
            nf = _font("Bold", int(num_w * 0.52))
            d.text((pad + num_w / 2, cy + num_w / 2), str(n), font=nf, fill=bg_c, anchor="mm")
            ty = y + max(0, (num_w - len(lines) * lh) // 2)
            for ln in lines:
                d.text((pad + num_w + 26, ty), ln, font=f, fill=txt_c); ty += lh
            y += max(len(lines) * lh, num_w) + int(30 * scale)
        if kind in ("subtitle",) or (kind == "title" and not any(bb[0] == "subtitle" for bb in blocks)):
            y += int(22 * scale)
            bx = (W - 120) // 2 if center else pad
            d.rounded_rectangle([bx, y, bx + 120, y + 10], radius=5, fill=acc_c)
            y += int(38 * scale)
    if spec.get("footer"):
        d.text((W // 2 if center else pad, H - pad + 10), spec["footer"], font=foot_f, fill=acc_c,
               anchor="ms" if center else "ls")
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def shaping_ok() -> bool:
    try:
        from PIL import features
        return bool(features.check("raqm"))
    except Exception:
        return False
