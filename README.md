# Nexora AI — web app (PWA) + Android app

*Your AI. Your Business. Your World.* — by Md Zahngir Hossain / SocialGrowthLab.

## What's here
| Path | What |
|---|---|
| `server.py` | FastAPI backend: `/api/chat` (SSE streaming), `/api/image`, `/api/video`, `/api/vision`, `/api/lead`, `/api/health` |
| `sglbot/` | AI/media/prompt logic copied from the Telegram bot (`/workspace/sgl-telegram-bot`), plus a Gemini tool-call fix and `HF_TOKEN` support |
| `static/` | Frontend (mobile-first dark chat UI, Bengali/English, markdown, photo upload, history in localStorage, PWA manifest + service worker + icons) |
| `android/` | Android WebView app (Gradle project). Signing key: `android/nexora-debug.keystore` (password `android`) — keep it, updates must use the same key |
| `android-build-output/NexoraAI.apk` | Built, signed APK |
| `Dockerfile`, `render.yaml`, `.env.example` | Deployment (Render free web service recommended) |
| `run-server.sh` | Box supervisor (auto-restart), logs in `logs/server.log` |

All API keys stay on the server (`.env` / host env vars). Rate limits per IP + daily global caps protect the free quotas.

## Run locally (box)
```
setsid nohup ./run-server.sh >/dev/null 2>&1 < /dev/null &   # http://localhost:8090
```
Stop: `kill $(cat logs/server-supervisor.pid); pkill -f "uvicorn server:app"`

## Deploy free on Render (no credit card)
1. Create a free GitHub account and push this folder to a new repo (the `.gitignore` keeps `.env`, logs and data out).
2. Sign up at https://render.com with GitHub → **New → Blueprint** → choose the repo (uses `render.yaml`, plan *free*, Docker).
3. Set env vars when asked: `GEMINI_API_KEY` (required), `TELEGRAM_BOT_TOKEN` + `ADMIN_CHAT_ID` (lead alerts), optional `HF_TOKEN`.
4. You get `https://nexora-ai.onrender.com` (or similar). Free plan sleeps after 15 min idle (first visit ~1 min to wake); disk is not persistent (leads still arrive on Telegram).

## Android
* Open the APK on the phone → allow "install unknown apps" → install.
* First launch asks for the server URL (enter the Render URL). Change it later from the menu → **⚙ Server URL**.
* Rebuild with a baked-in URL:
```
export JAVA_HOME=/workspace/tools/jdk17 ANDROID_HOME=/workspace/tools/android-sdk
cd android && ./gradlew assembleDebug -PnexoraUrl=https://YOUR-APP.onrender.com
cp app/build/outputs/apk/debug/app-debug.apk ../android-build-output/NexoraAI.apk
```

## Telegram token on Render
The web app never polls Telegram. `TELEGRAM_BOT_TOKEN` + `ADMIN_CHAT_ID` are only used to *send* lead alerts (`sendMessage`), so it is safe to use the same token the Telegram bot already polls with elsewhere — no `getUpdates` conflict.

## Voice (v1.1)
- Tap 🎤 in the composer to record (up to 60 s). The browser records 16 kHz mono WAV and posts it to `POST /api/voice`
  (multipart: `file`, `mode`, `session_id`, `history`). The server transcribes it with Gemini, answers with the same
  mode logic, and returns `{transcript, reply, audio}` where `audio` is an MP3 data URL made with the free edge-tts voices
  (`bn-BD-NabanitaNeural` for Bengali, `en-US-AvaNeural` for English).
- `POST /api/tts {text}` powers the 🔊 Listen button under any reply. Audio is kept in memory only, never in localStorage.
- Android 1.1.0 asks for the microphone permission and only grants it to the configured Nexora server.

## Photo editing & image reliability (v1.2)
- Send a photo with an edit request ("change the background to a beach", "ব্যাকগ্রাউন্ড সরাও", "make it cartoon").
  Gemini routes the request (`photoedit.plan_edit`) to: background removal (free HF Spaces BiRefNet / BRIA RMBG /
  rembg-on-CPU, local `rembg` on the bot box), background replacement (cutout + new background, composited in the
  browser on Vercel or with Pillow in the bot), or instruction edits (free FLUX.1-Kontext Space, small daily quota).
- Pollinations rate-limit placeholders (402/429/503 + "Free limit reached" image) are detected; the app waits for
  Retry-After, retries, then falls back to `POST /api/image/fallback` (free FLUX.1-schnell Space).
- Android 1.2.0 saves edited images (data: URLs) to Download/Nexora.
