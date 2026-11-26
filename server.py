"""Nexora AI web backend (FastAPI). Reuses the Telegram bot's AI/media logic in sglbot/."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

from sglbot import ai, media, photoedit, prompts, voice

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("nexora")

GEMINI_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
AI_MODEL = (os.getenv("AI_MODEL") or "").strip() or "gemini-3.5-flash-lite"
GEMINI_BASE = (os.getenv("GEMINI_BASE_URL") or "").strip() or "https://generativelanguage.googleapis.com/v1beta/openai/"
TG_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
ADMIN_CHAT_ID = (os.getenv("ADMIN_CHAT_ID") or "").strip()
ON_VERCEL = bool(os.getenv("VERCEL"))
# Serverless filesystems are read-only except /tmp, and /tmp is not shared between instances.
DATA_DIR = Path(os.getenv("DATA_DIR") or ("/tmp/nexora-data" if ON_VERCEL else ROOT / "data"))
# Return generated media inline (data: URL) when files can't be served back reliably (serverless).
MEDIA_INLINE = (os.getenv("MEDIA_INLINE") or ("1" if ON_VERCEL else "0")) == "1"
# Pollinations refuses anonymous requests from cloud/datacenter IPs (HTTP 402), so on serverless
# hosts the browser loads the free image URL directly instead of the server downloading it.
IMAGE_CLIENT_SIDE = (os.getenv("IMAGE_CLIENT_SIDE") or ("1" if ON_VERCEL else "0")) == "1"
VIDEO_TIMEOUT = int(os.getenv("VIDEO_TIMEOUT") or (110 if ON_VERCEL else 180))
MEDIA_DIR = DATA_DIR / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
LEADS_CSV = DATA_DIR / "leads.csv"
MAX_HISTORY = 20
MAX_MEDIA_FILES = 300


class _Cfg:  # minimal stand-in for sglbot.config.Config used by ai.complete
    ai_model = AI_MODEL


CFG = _Cfg()
client = OpenAI(api_key=GEMINI_KEY or "missing", base_url=GEMINI_BASE, timeout=60.0)

APP_NOTE = """
App context: You are running inside the Nexora AI web/Android app (not Telegram).
The user switches modes with tabs at the top: Chat, Content, Growth, Image, Video. Do not mention slash commands.
Use Markdown formatting (headings, bullet lists, bold) where it helps readability.
IMPORTANT: Always answer in the language of the user's LATEST message — English message → English reply; Bengali message → Bengali reply.
""".strip()

MODES = ("chat", "caption", "growth", "image", "video")

# ---------------------------------------------------------------- rate limit
_LIMITS: dict[str, list[tuple[int, int]]] = {
    # bucket: [(max_requests, window_seconds), ...]
    "chat": [(20, 60), (300, 86400)],
    "vision": [(8, 60), (60, 86400)],
    "image": [(6, 60), (60, 86400)],
    "video": [(2, 120), (10, 86400)],
    "lead": [(5, 60), (30, 86400)],
    "voice": [(10, 60), (120, 86400)],
    "tts": [(15, 60), (200, 86400)],
    "edit": [(4, 60), (40, 86400)],
    "imgfb": [(4, 60), (40, 86400)],
}
_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_rl_lock = threading.Lock()


PROXY_HOPS = max(1, int(os.getenv("TRUST_PROXY_HOPS", "1") or 1))
# Whole-server daily caps (all visitors together) to protect the free quotas.
_GLOBAL_DAILY = {"chat": 1500, "vision": 300, "image": 400, "video": 40, "lead": 200, "voice": 800, "tts": 1000, "edit": 300, "imgfb": 300}


def client_ip(request: Request) -> str:
    cf = request.headers.get("cf-connecting-ip")  # set by Cloudflare, not spoofable through it
    if cf:
        return cf.strip()
    xff = [p.strip() for p in (request.headers.get("x-forwarded-for") or "").split(",") if p.strip()]
    if xff:  # rightmost entries are added by our own proxies; leftmost can be spoofed
        return xff[-min(PROXY_HOPS, len(xff))]
    return request.client.host if request.client else "unknown"


def check_rate(request: Request, bucket: str) -> None:
    ip = client_ip(request)
    now = time.time()
    rules = _LIMITS[bucket]
    longest = max(w for _, w in rules)
    with _rl_lock:
        g = _hits[(bucket, "*global*")]
        while g and now - g[0] > 86400:
            g.popleft()
        if len(g) >= _GLOBAL_DAILY[bucket]:
            raise HTTPException(
                status_code=429,
                detail="আজকের ফ্রি সীমা শেষ, আগামীকাল আবার চেষ্টা করুন। / Today's free limit is reached — please try again tomorrow.",
            )
        q = _hits[(bucket, ip)]
        while q and now - q[0] > longest:
            q.popleft()
        for limit, window in rules:
            if sum(1 for t in q if now - t <= window) >= limit:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "অনেক বেশি অনুরোধ হয়েছে, একটু পরে আবার চেষ্টা করুন। "
                        "Too many requests — please wait a bit and try again."
                    ),
                )
        q.append(now)
        g.append(now)


# ---------------------------------------------------------------- sessions (growth lead drafts)
_sessions: dict[str, dict[str, Any]] = {}
_sess_lock = threading.Lock()


def session_lead(sid: str) -> dict:
    with _sess_lock:
        s = _sessions.setdefault(sid, {"lead": {}, "submitted": False, "ts": time.time()})
        s["ts"] = time.time()
        if len(_sessions) > 5000:  # drop oldest
            for k, _ in sorted(_sessions.items(), key=lambda kv: kv[1]["ts"])[:1000]:
                _sessions.pop(k, None)
        return s


# ---------------------------------------------------------------- helpers
def clean_history(history: list[dict] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in (history or [])[-MAX_HISTORY:]:
        role = item.get("role")
        content = str(item.get("content") or "")[:4000]
        if role in ("user", "assistant") and content.strip():
            out.append({"role": role, "content": content})
    return out


def language_hint(text: str) -> str:
    if media.has_bengali(text):
        return "The user's latest message is in Bengali, so reply in Bengali."
    if re.search(r"[A-Za-z]{3,}", text or ""):
        return "The user's latest message is in English, so reply in English only (no Bengali)."
    return ""


def system_prompt(mode: str, lead: dict | None = None) -> str:
    if mode == "caption":
        base = prompts.caption_system_prompt()
    elif mode == "growth":
        base = prompts.growth_system_prompt(lead)
    else:
        base = prompts.chat_system_prompt()
    return f"{base}\n\n{APP_NOTE}"


def save_media(data: bytes, ext: str) -> str:
    if MEDIA_INLINE:
        import base64
        mime = {"png": "image/png", "jpg": "image/jpeg", "mp4": "video/mp4"}.get(ext, "application/octet-stream")
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    name = f"{uuid.uuid4().hex}.{ext}"
    (MEDIA_DIR / name).write_bytes(data)
    files = sorted(MEDIA_DIR.iterdir(), key=lambda p: p.stat().st_mtime)
    for old in files[:-MAX_MEDIA_FILES]:
        try:
            old.unlink()
        except OSError:
            pass
    return f"/media/{name}"


def append_lead_csv(lead: dict, source: str, session: str) -> None:
    cols = ["timestamp", "source", "session", "name", "ig_handle", "budget", "contact"]
    new = not LEADS_CSV.exists() or LEADS_CSV.stat().st_size == 0
    with _sess_lock, LEADS_CSV.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        if new:
            w.writeheader()
        w.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source,
            "session": session,
            **{k: (lead.get(k) or "").strip() for k in ("name", "ig_handle", "budget", "contact")},
        })


def notify_admin(lead: dict, source: str) -> bool:
    if not (TG_TOKEN and ADMIN_CHAT_ID):
        return False
    text = (
        f"New SocialGrowthLab lead (Nexora app — {source})\n"
        f"Name: {lead.get('name') or '-'}\n"
        f"Instagram: {lead.get('ig_handle') or '-'}\n"
        f"Budget: {lead.get('budget') or '-'}\n"
        f"Contact: {lead.get('contact') or '-'}"
    )
    data = urllib.parse.urlencode({"chat_id": ADMIN_CHAT_ID, "text": text}).encode()
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data, timeout=15
        ) as resp:
            return resp.status == 200
    except Exception:
        logger.exception("Telegram admin notify failed")
        return False


def record_lead(lead: dict, source: str, session: str) -> bool:
    append_lead_csv(lead, source, session)
    return notify_admin(lead, source)


def make_lead_tool(sid: str):
    def handle(name: str, args: dict[str, Any]) -> str:
        if name != "save_lead":
            return f"Unknown tool: {name}"
        s = session_lead(sid)
        lead = s["lead"]
        before = dict(lead)
        for k in ("name", "ig_handle", "budget", "contact"):
            v = (args.get(k) or "").strip()
            if v:
                lead[k] = v
        if all(lead.get(k) for k in ("name", "ig_handle", "budget", "contact")):
            changed = lead != before
            if not s["submitted"] or changed:
                record_lead(lead, "growth-chat", sid)
                s["submitted"] = True
                return ("Lead saved as complete. Thank the user in their language and say "
                        "Md Zahngir Hossain will follow up. Share the Upwork link.")
            return "Lead already saved as complete. No new fields to add."
        missing = [k for k in ("name", "ig_handle", "budget", "contact") if not lead.get(k)]
        return ("Lead draft updated. Still missing: " + ", ".join(missing)
                + ". Ask for the missing fields naturally, one or two at a time.")
    return handle


def friendly_ai_error() -> str:
    return ("দুঃখিত, AI এই মুহূর্তে ব্যস্ত। একটু পরে আবার চেষ্টা করুন।\n\n"
            "Sorry, the AI is busy right now. Please try again in a moment.")


# ---------------------------------------------------------------- app
app = FastAPI(title="Nexora AI", docs_url=None, redoc_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


class ChatIn(BaseModel):
    message: str = Field(..., max_length=6000)
    mode: str = "chat"
    session_id: str = Field("anon", max_length=80)
    history: list[dict] = Field(default_factory=list)
    stream: bool = True


@app.get("/api/health")
def health():
    return {"ok": True, "host": "vercel" if ON_VERCEL else "server", "model": AI_MODEL, "ai": bool(GEMINI_KEY), "lead_alerts": bool(TG_TOKEN and ADMIN_CHAT_ID)}


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    check_rate(request, "chat")
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "empty message")
    mode = body.mode if body.mode in MODES else "chat"

    # Natural-language media requests from chat-like modes are routed to the media endpoints.
    if mode in ("chat", "caption"):
        if media.looks_like_video_request(text):
            return JSONResponse({"action": "video", "prompt": media.extract_video_prompt(text) or text})
        if media.looks_like_image_request(text):
            return JSONResponse({"action": "image", "prompt": media.extract_image_prompt(text) or text})
    if mode == "image":
        return JSONResponse({"action": "image", "prompt": text})
    if mode == "video":
        return JSONResponse({"action": "video", "prompt": text})

    history = clean_history(body.history)
    hint = language_hint(text)

    if mode == "growth":
        s = session_lead(body.session_id)
        try:
            reply = await asyncio.to_thread(
                ai.complete, client, CFG,
                system_prompt=system_prompt("growth", s["lead"]) + "\n" + hint,
                history=history, user_message=text,
                tools=ai.growth_tools(), on_tool=make_lead_tool(body.session_id),
            )
        except Exception:
            logger.exception("growth chat failed")
            reply = friendly_ai_error()
        return JSONResponse({"reply": reply or friendly_ai_error(), "lead": s["lead"], "lead_saved": s["submitted"]})

    messages = [{"role": "system", "content": system_prompt(mode) + "\n" + hint}, *history, {"role": "user", "content": text}]

    if not body.stream:
        try:
            reply = await asyncio.to_thread(
                ai.complete, client, CFG, system_prompt=system_prompt(mode) + "\n" + hint, history=history, user_message=text
            )
        except Exception:
            logger.exception("chat failed")
            reply = friendly_ai_error()
        return JSONResponse({"reply": reply or friendly_ai_error()})

    def gen():
        for attempt in range(3):
            sent = False
            try:
                stream = client.chat.completions.create(
                    model=AI_MODEL, messages=messages, temperature=0.7, stream=True
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        sent = True
                        yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
                yield "data: {\"done\": true}\n\n"
                return
            except Exception as exc:
                logger.warning("stream attempt %s failed: %s", attempt + 1, exc)
                if sent or attempt == 2:
                    yield f"data: {json.dumps({'error': friendly_ai_error()}, ensure_ascii=False)}\n\n"
                    return
                time.sleep(1.5 * (attempt + 1))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class MediaIn(BaseModel):
    prompt: str = Field(..., max_length=1500)


@app.post("/api/image")
async def image(body: MediaIn, request: Request):
    check_rate(request, "image")
    prompt = media.extract_image_prompt(body.prompt) or body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "empty prompt")
    if IMAGE_CLIENT_SIDE:
        import random
        q = urllib.parse.quote(prompt[:800], safe="")
        seed = random.randint(1, 2_000_000_000)
        url = f"{media.POLLINATIONS_BASE}{q}?width=1024&height=1024&nologo=true&seed={seed}"
        return {"url": url, "source": "pollinations-direct", "prompt": prompt}
    try:
        res = await asyncio.to_thread(media.generate_image, GEMINI_KEY, prompt)
    except Exception:
        logger.exception("image failed")
        raise HTTPException(502, "দুঃখিত, এখন ছবি বানানো গেল না। একটু পরে আবার চেষ্টা করুন। / Sorry, image generation failed — please try again.")
    ext = "png" if "png" in res.mime else "jpg"
    return {"url": save_media(res.data, ext), "source": res.source, "prompt": prompt}


@app.post("/api/video")
async def video(body: MediaIn, request: Request):
    check_rate(request, "video")
    prompt = media.extract_video_prompt(body.prompt) or body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "empty prompt")
    try:
        res = await asyncio.wait_for(
            asyncio.to_thread(media.generate_video, prompt), timeout=VIDEO_TIMEOUT
        )
    except Exception as exc:
        logger.exception("video failed")
        if isinstance(exc, asyncio.TimeoutError):
            raise HTTPException(504, "ভিডিও তৈরিতে বেশি সময় লাগছে, একটু পরে আবার চেষ্টা করুন। / The free video queue is slow right now — please try again shortly.")
        if "quota" in str(exc).lower():
            raise HTTPException(503, "আজকের ফ্রি ভিডিও কোটা শেষ হয়ে গেছে, কিছুক্ষণ পরে (বা আগামীকাল) আবার চেষ্টা করুন।\n\n"
                                     "Today's free video quota is used up — please try again later (or tomorrow).")
        raise HTTPException(502, media.video_fail_message(body.prompt).replace("/video", "Video mode"))
    return {"url": save_media(res.data, "mp4"), "source": res.source, "prompt": prompt}


@app.post("/api/vision")
async def vision(request: Request, file: UploadFile = File(...), question: str = Form("")):
    check_rate(request, "vision")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "ছবি ৮MB-এর কম হতে হবে / Image must be under 8 MB")
    # Photo + edit request ("change the background to a beach", "ব্যাকগ্রাউন্ড সরাও") -> real editing tools.
    if question.strip():
        plan = await asyncio.to_thread(photoedit.plan_edit, GEMINI_KEY, AI_MODEL, question.strip()[:1500])
        if plan.op != "none":
            check_rate(request, "edit")
            return await _photo_edit(data, plan, question.strip())
    q = question.strip() or (
        "এই ছবিটি পরিষ্কার করে বর্ণনা করুন। কোনো লেখা থাকলে তা লিখে দিন। "
        "Describe this image clearly. Transcribe any visible text. Reply in the user's language (Bengali if unclear)."
    )
    try:
        reply = await asyncio.to_thread(
            media.understand_image, GEMINI_KEY, AI_MODEL, data, file.content_type or "image/jpeg",
            q[:2000] + "\n\n(System note: you can only look at this photo. Never claim you edited, changed or generated an image.)"
        )
    except Exception:
        logger.exception("vision failed")
        raise HTTPException(502, "দুঃখিত, ছবিটি এখন পড়া যাচ্ছে না। / Sorry, I couldn't read that photo right now.")
    return {"reply": reply}


VOICE_NOTE = (
    "The user sent this as a VOICE message and your reply will be read aloud. "
    "Answer conversationally and fairly briefly (about 40-120 words), with no tables or code blocks."
)


async def _audio_reply(text: str) -> str:
    try:
        mp3 = await voice.synthesize_async(text)
    except Exception:
        logger.exception("tts failed")
        return ""
    import base64
    return "data:audio/mpeg;base64," + base64.b64encode(mp3).decode()


@app.post("/api/voice")
async def voice_chat(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("chat"),
    session_id: str = Form("anon"),
    history: str = Form("[]"),
):
    check_rate(request, "voice")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty audio")
    if len(data) > 4 * 1024 * 1024:
        raise HTTPException(413, "অডিও খুব বড় (১ মিনিটের কম রাখুন) / Audio too long — keep it under a minute")
    mode = mode if mode in MODES else "chat"
    session_id = (session_id or "anon")[:80]
    try:
        transcript = await asyncio.to_thread(
            voice.transcribe, GEMINI_KEY, AI_MODEL, data, (file.content_type or "audio/wav")
        )
    except Exception:
        logger.exception("transcribe failed")
        raise HTTPException(502, "দুঃখিত, অডিওটি এখন বোঝা যাচ্ছে না। / Sorry, I couldn't understand the audio right now.")
    if not transcript:
        return {"transcript": "", "reply": "অডিওতে কোনো কথা শুনতে পাইনি, আবার বলুন। / I couldn't hear any speech — please try again.", "audio": ""}

    if mode in ("chat", "caption"):
        if media.looks_like_video_request(transcript):
            return {"transcript": transcript, "action": "video", "prompt": media.extract_video_prompt(transcript) or transcript}
        if media.looks_like_image_request(transcript):
            return {"transcript": transcript, "action": "image", "prompt": media.extract_image_prompt(transcript) or transcript}
    if mode in ("image", "video"):
        return {"transcript": transcript, "action": mode, "prompt": transcript}

    try:
        hist = clean_history(json.loads(history or "[]"))
    except Exception:
        hist = []
    hint = language_hint(transcript) + "\n" + VOICE_NOTE
    out: dict[str, Any] = {"transcript": transcript}
    try:
        if mode == "growth":
            s = session_lead(session_id)
            reply = await asyncio.to_thread(
                ai.complete, client, CFG,
                system_prompt=system_prompt("growth", s["lead"]) + "\n" + hint,
                history=hist, user_message=transcript,
                tools=ai.growth_tools(), on_tool=make_lead_tool(session_id),
            )
            out.update(lead=s["lead"], lead_saved=s["submitted"])
        else:
            reply = await asyncio.to_thread(
                ai.complete, client, CFG, system_prompt=system_prompt(mode) + "\n" + hint,
                history=hist, user_message=transcript,
            )
    except Exception:
        logger.exception("voice chat failed")
        reply = ""
    reply = reply or friendly_ai_error()
    out["reply"] = reply
    out["audio"] = await _audio_reply(reply)
    return out


class TtsIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=6000)


@app.post("/api/tts")
async def tts(body: TtsIn, request: Request):
    check_rate(request, "tts")
    audio = await _audio_reply(body.text)
    if not audio:
        raise HTTPException(502, "দুঃখিত, এখন ভয়েস তৈরি করা গেল না। / Sorry, couldn't create the voice right now.")
    return {"audio": audio}


async def _photo_edit(data: bytes, plan, request_text: str) -> dict:
    bn = media.has_bengali(request_text)
    try:
        if plan.op == "remove_bg":
            png, src = await asyncio.to_thread(photoedit.remove_background, data)
            return {"edit": True, "op": "remove_bg", "image": photoedit.data_url(png, "image/png"), "source": src,
                    "reply": "✅ ব্যাকগ্রাউন্ড সরানো হয়েছে (স্বচ্ছ PNG)।" if bn else "✅ Background removed (transparent PNG)."}
        if plan.op == "replace_bg":
            png, src = await asyncio.to_thread(photoedit.remove_background, data)
            from PIL import Image
            import io as _io
            w, h = Image.open(_io.BytesIO(png)).size
            scale = 1024 / max(w, h)
            bw, bh = max(256, int(w * scale) // 32 * 32), max(256, int(h * scale) // 32 * 32)
            bg_prompt = photoedit.background_prompt(plan.background)
            # The browser fetches the free Pollinations background (Vercel's IPs are refused), checks it
            # is a real image (not the rate-limit placeholder), and composites it on a canvas.
            return {"edit": True, "op": "replace_bg", "cutout": photoedit.data_url(png, "image/png"), "source": src,
                    "bg_prompt": bg_prompt, "bg_url": photoedit.pollinations_url(bg_prompt, bw, bh),
                    "width": w, "height": h, "background": plan.background,
                    "reply": (f"✅ নতুন ব্যাকগ্রাউন্ড: {plan.background}" if bn else f"✅ New background: {plan.background}")}
        out, src = await asyncio.wait_for(
            asyncio.to_thread(photoedit.instruct_edit, data, plan.instruction or request_text), timeout=VIDEO_TIMEOUT
        )
        return {"edit": True, "op": "edit", "image": photoedit.data_url(out, "image/jpeg"), "source": src,
                "reply": "✅ " + (plan.instruction or request_text)}
    except (photoedit.EditError, asyncio.TimeoutError) as exc:
        logger.warning("photo edit failed: %s", exc)
        if plan.op == "edit":
            msg = ("দুঃখিত, এই ধরনের এডিটের ফ্রি সার্ভার এখন ব্যস্ত বা আজকের ফ্রি সীমা শেষ, তাই ছবিটা বদলানো হয়নি। "
                   "ব্যাকগ্রাউন্ড বদলানো বা সরানো এখনো কাজ করবে, অথবা কিছুক্ষণ পরে আবার চেষ্টা করুন।"
                   if bn else "Sorry, the free server for this kind of edit is busy or out of today's free quota, so the photo was NOT changed. "
                   "Background change/removal still works, or try again later.")
        else:
            msg = ("দুঃখিত, ফ্রি ব্যাকগ্রাউন্ড-রিমুভ সার্ভার এখন সাড়া দিচ্ছে না, তাই ছবিটা বদলানো হয়নি। একটু পরে আবার চেষ্টা করুন।"
                   if bn else "Sorry, the free background-removal server isn't responding, so the photo was NOT changed. Please try again shortly.")
        raise HTTPException(503, msg)
    except Exception:
        logger.exception("photo edit crashed")
        raise HTTPException(502, "দুঃখিত, ছবি এডিট করা গেল না। / Sorry, the photo edit failed — please try again.")


class FallbackImageIn(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1500)
    width: int = Field(1024, ge=256, le=1280)
    height: int = Field(1024, ge=256, le=1280)


@app.post("/api/image/fallback")
async def image_fallback(body: FallbackImageIn, request: Request):
    """Used by the browser when Pollinations is rate-limited for the visitor: free FLUX.1-schnell Space."""
    check_rate(request, "imgfb")
    got = await asyncio.to_thread(
        photoedit.generate_image_free, body.prompt, body.width, body.height, not IMAGE_CLIENT_SIDE
    )
    if not got:
        raise HTTPException(503, "ফ্রি ছবি-সার্ভারগুলো এখন ব্যস্ত, কয়েক সেকেন্ড পরে আবার চেষ্টা করুন। / "
                                 "The free image servers are busy right now — please try again in a few seconds.")
    return {"url": photoedit.data_url(got[0], "image/jpeg"), "source": got[1]}


class LeadIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    ig_handle: str = Field(..., min_length=1, max_length=200)
    budget: str = Field(..., min_length=1, max_length=120)
    contact: str = Field(..., min_length=3, max_length=200)
    session_id: str = Field("anon", max_length=80)


@app.post("/api/lead")
async def lead(body: LeadIn, request: Request):
    check_rate(request, "lead")
    data = body.model_dump()
    alerted = await asyncio.to_thread(record_lead, data, "lead-form", body.session_id)
    return {"ok": True, "alerted": alerted}


app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


@app.get("/sw.js")
def sw():
    return FileResponse(ROOT / "static" / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
