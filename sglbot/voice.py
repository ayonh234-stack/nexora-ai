"""Free voice support: speech-to-text via Gemini (free tier) and text-to-speech via edge-tts."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from sglbot.media import NATIVE_BASE, _http_json, has_bengali

logger = logging.getLogger(__name__)

VOICE_BN = "bn-BD-NabanitaNeural"
VOICE_EN = "en-US-AvaNeural"
MAX_TTS_CHARS = 1500

# Gemini accepts these audio MIME types inline.
_GEMINI_AUDIO = {"audio/wav", "audio/x-wav", "audio/mp3", "audio/mpeg", "audio/aiff", "audio/aac",
                 "audio/ogg", "audio/flac", "audio/opus"}

TRANSCRIBE_PROMPT = (
    "Transcribe this voice message exactly as spoken, in its original language and script "
    "(Bengali in Bengali script, English in English). Output only the transcript text, "
    "no labels, no translation, no commentary. If there is no speech, output: [no speech]"
)


def _norm_mime(mime: str) -> str:
    mime = (mime or "").split(";")[0].strip().lower()
    if mime in ("audio/x-wav", "audio/wave", "audio/vnd.wave"):
        return "audio/wav"
    if mime in ("audio/mpeg3", "audio/x-mp3"):
        return "audio/mp3"
    if mime in ("audio/x-m4a", "audio/m4a", "audio/mp4"):
        return "audio/aac"
    return mime


def convert_with_ffmpeg(data: bytes, out_ext: str, args: list[str]) -> bytes | None:
    if not shutil.which("ffmpeg"):
        return None
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.bin"
        dst = Path(td) / f"out.{out_ext}"
        src.write_bytes(data)
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), *args, str(dst)],
            capture_output=True, timeout=60,
        )
        if proc.returncode != 0 or not dst.exists():
            logger.warning("ffmpeg failed: %s", proc.stderr.decode(errors="ignore")[:300])
            return None
        return dst.read_bytes()


def transcribe(api_key: str, model: str, audio: bytes, mime: str) -> str:
    """Return the spoken text using Gemini's native audio understanding (free tier)."""
    if not api_key:
        raise RuntimeError("missing Gemini API key")
    mime = _norm_mime(mime)
    if mime not in _GEMINI_AUDIO:
        # e.g. audio/webm from browsers: convert to mp3 when ffmpeg exists.
        converted = convert_with_ffmpeg(audio, "mp3", ["-ac", "1", "-ar", "16000"])
        if converted:
            audio, mime = converted, "audio/mp3"
        else:
            mime = "audio/ogg" if mime.endswith("webm") else (mime or "audio/ogg")
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": TRANSCRIBE_PROMPT},
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}},
            ],
        }],
        "generationConfig": {"temperature": 0},
    }
    last = None
    for attempt in range(3):
        status, obj = _http_json("POST", f"{NATIVE_BASE}/{model}:generateContent",
                                 {"x-goog-api-key": api_key}, body, timeout=60)
        if status == 200:
            parts = ((obj.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            text = " ".join((p.get("text") or "").strip() for p in parts if p.get("text")).strip()
            if text.strip("[] .").lower() == "no speech":
                return ""
            return text
        last = (obj.get("error") or {}).get("message") or f"HTTP {status}"
        if status in (429, 500, 503) and attempt < 2:
            import time
            time.sleep(1.5 * (attempt + 1))
            continue
        break
    raise RuntimeError(f"transcription failed: {last}")


def speech_text(markdown: str) -> str:
    """Strip markdown/URLs/emojis so the reply reads naturally."""
    t = markdown or ""
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[#*_`>|~]+", " ", t)
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t).strip()
    if len(t) > MAX_TTS_CHARS:
        cut = t[:MAX_TTS_CHARS]
        end = max(cut.rfind("।"), cut.rfind(". "), cut.rfind("\n"))
        t = cut[: end + 1] if end > 400 else cut
    return t


def pick_voice(text: str) -> str:
    return VOICE_BN if has_bengali(text) else VOICE_EN


VOICE_FALLBACKS = {
    VOICE_BN: [VOICE_BN, VOICE_BN, "bn-IN-TanishaaNeural", "bn-BD-PradeepNeural", VOICE_BN],
    VOICE_EN: [VOICE_EN, VOICE_EN, "en-US-JennyNeural"],
}


async def _edge_once(clean: str, voice: str) -> bytes:
    import edge_tts

    comm = edge_tts.Communicate(clean, voice)
    out = bytearray()
    async for chunk in comm.stream():
        if chunk.get("type") == "audio":
            out.extend(chunk["data"])
    if not out:
        raise RuntimeError("TTS returned no audio")
    return bytes(out)


async def synthesize_async(text: str, voice: str | None = None) -> bytes:
    """Text -> MP3 bytes with the free edge-tts voices.

    The free endpoint sometimes answers with no audio (seen intermittently from cloud IPs for
    Bengali), so retry and fall back to a sibling voice before giving up.
    """
    clean = speech_text(text)
    if not clean:
        raise ValueError("nothing to speak")
    voice = voice or pick_voice(clean)
    chain = VOICE_FALLBACKS.get(voice, [voice, voice])
    last: Exception | None = None
    for i, v in enumerate(chain):
        try:
            return await _edge_once(clean, v)
        except Exception as exc:  # NoAudioReceived, WebSocket errors, ...
            last = exc
            logger.warning("edge-tts attempt %s with %s failed: %s", i + 1, v, type(exc).__name__)
            await asyncio.sleep(0.4 * (i + 1))
    raise RuntimeError(f"TTS failed: {last}")


def synthesize(text: str, voice: str | None = None) -> bytes:
    return asyncio.run(synthesize_async(text, voice))


def mp3_to_ogg_opus(mp3: bytes) -> bytes | None:
    return convert_with_ffmpeg(mp3, "ogg", ["-c:a", "libopus", "-b:a", "32k", "-ac", "1", "-ar", "48000"])
