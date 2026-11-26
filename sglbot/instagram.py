"""Official Instagram Graph API client for the owner's account (no passwords, no scraping).

Works with both official flavours:
  * Instagram API with Instagram Login  -> tokens start with "IG", host graph.instagram.com
  * Instagram API with Facebook Login   -> tokens start with "EAA", host graph.facebook.com (IG account linked to a Page)
Credentials live in the encrypted vault: IG_ACCESS_TOKEN, IG_USER_ID (+ optional IG_APP_ID / IG_APP_SECRET / IG_PAGE_ID / IG_PAGE_TOKEN).
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from sglbot import store, vault

logger = logging.getLogger(__name__)
API_VERSION = "v23.0"
PUBLIC_BASE = (os.getenv("PUBLIC_BASE_URL") or "https://nexora-ai-nexora-59d1.vercel.app").rstrip("/")
SETTINGS_DEFAULT = {"auto_post": False, "auto_reply": False, "auto_hide_spam": False}


class IGError(RuntimeError):
    pass


# ---------------------------------------------------------------- credentials / HTTP
def _creds(max_age: float = 0) -> dict:
    try:
        e = vault._load(max_age)
    except vault.VaultError:
        return {}
    return {k: v.get("value", "") for k, v in e.items() if k.startswith("IG_")}


def kind_of(token: str) -> str:
    return "instagram" if (token or "").startswith("IG") else "facebook"


def _base(kind: str) -> str:
    override = os.getenv("IG_GRAPH_BASE")  # only for local tests against a mock Graph server
    if override:
        return override.rstrip("/")
    return f"https://graph.instagram.com/{API_VERSION}" if kind == "instagram" else f"https://graph.facebook.com/{API_VERSION}"


def call(method: str, path: str, token: str, params: dict | None = None, kind: str | None = None, timeout: float = 40,
         raw_path: bool = False) -> dict:
    kind = kind or kind_of(token)
    base = _base(kind)
    if raw_path and not os.getenv("IG_GRAPH_BASE"):
        base = base.rsplit("/", 1)[0]  # endpoints without the version prefix (refresh_access_token)
    q = {k: (json.dumps(v) if isinstance(v, (list, dict)) else str(v)) for k, v in (params or {}).items() if v is not None}
    q["access_token"] = token
    url = f"{base}/{path.lstrip('/')}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(q)
    else:
        data = urllib.parse.urlencode(q).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "NexoraAI/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        body = (exc.read() or b"").decode("utf-8", "ignore")
    except Exception as exc:
        raise IGError(f"network error: {type(exc).__name__}") from None
    try:
        j = json.loads(body) if body.strip() else {}
    except Exception:
        raise IGError(f"bad response: {body[:120]}") from None
    if isinstance(j, dict) and j.get("error"):
        err = j["error"]
        msg = err.get("error_user_msg") or err.get("message") or str(err)
        raise IGError(f"{msg} (code {err.get('code')})".replace(token, "[token]"))
    return j


def _client(max_age: float = 0) -> tuple[str, str, str]:
    c = _creds(max_age)
    tok, uid = c.get("IG_ACCESS_TOKEN", ""), c.get("IG_USER_ID", "")
    if not tok or not uid:
        raise IGError("Instagram is not connected yet — paste the token in Nexora (Instagram screen or /ig token)")
    return tok, uid, kind_of(tok)


def connected(max_age: float = 300) -> bool:
    c = _creds(max_age)
    return bool(c.get("IG_ACCESS_TOKEN") and c.get("IG_USER_ID"))


def state(max_age: float = 0) -> dict:
    return store.get("ig/state", {}, max_age=max_age) or {}


def settings(max_age: float = 0) -> dict:
    return {**SETTINGS_DEFAULT, **(store.get("ig/settings", {}, max_age=max_age) or {})}


def save_settings(**kw) -> dict:
    s = settings()
    s.update({k: bool(v) for k, v in kw.items() if k in SETTINGS_DEFAULT and v is not None})
    store.put("ig/settings", s)
    return s


# ---------------------------------------------------------------- connect / refresh
def connect(token: str, user_id: str = "", app_id: str = "", app_secret: str = "") -> dict:
    token = re.sub(r"\s+", "", token or "")
    if len(token) < 20:
        raise IGError("that does not look like an access token")
    kind = kind_of(token)
    expires_in = None
    page_id = page_token = ""
    if kind == "instagram":
        if app_secret:  # short-lived (1 h) -> long-lived (60 days); harmless if it is already long-lived
            try:
                j = call("GET", "access_token", token, {"grant_type": "ig_exchange_token", "client_secret": app_secret}, kind, raw_path=True)
                token, expires_in = j.get("access_token", token), j.get("expires_in")
            except IGError as exc:
                logger.info("IG exchange skipped: %s", exc)
        me = call("GET", "me", token, {"fields": "user_id,username,account_type,followers_count,media_count"}, kind)
        uid = str(user_id or me.get("user_id") or me.get("id") or "")
        username = me.get("username", "")
    else:
        if app_id and app_secret:
            try:
                j = call("GET", "oauth/access_token", token, {"grant_type": "fb_exchange_token", "client_id": app_id,
                                                              "client_secret": app_secret, "fb_exchange_token": token}, kind)
                token, expires_in = j.get("access_token", token), j.get("expires_in")
            except IGError as exc:
                logger.info("FB exchange skipped: %s", exc)
        uid = str(user_id or "")
        pages = call("GET", "me/accounts", token, {"fields": "id,name,access_token,instagram_business_account{id,username}"}, kind)
        for p in pages.get("data", []):
            ig = p.get("instagram_business_account") or {}
            if ig.get("id") and (not uid or ig["id"] == uid):
                uid, page_id, page_token = ig["id"], p.get("id", ""), p.get("access_token", "")
                break
        if not uid:
            raise IGError("no Instagram professional account linked to your Facebook Pages was found "
                          "(link the IG account to a Page, and grant pages_show_list + instagram_basic)")
        me = call("GET", uid, token, {"fields": "username,followers_count,media_count"}, kind)
        username = me.get("username", "")
    if not uid:
        raise IGError("could not read the Instagram user id")
    vault.set_entry("IG_ACCESS_TOKEN", token, f"Instagram token ({kind} login)")
    vault.set_entry("IG_USER_ID", uid, f"@{username}")
    if app_id:
        vault.set_entry("IG_APP_ID", app_id, "Meta app id")
    if app_secret:
        vault.set_entry("IG_APP_SECRET", app_secret, "Meta app secret")
    if page_id:
        vault.set_entry("IG_PAGE_ID", page_id, "Facebook Page id")
    if page_token:
        vault.set_entry("IG_PAGE_TOKEN", page_token, "Facebook Page token (DMs)")
    now = time.time()
    st = {"username": username, "user_id": uid, "kind": kind, "connected_at": now, "refreshed_at": now,
          "expires_at": now + float(expires_in) if expires_in else (now + 60 * 86400 if kind == "instagram" else None),
          "followers": me.get("followers_count"), "media_count": me.get("media_count"), "page_id": page_id}
    store.put("ig/state", st)
    return status(st)


def disconnect() -> None:
    for n in ("IG_ACCESS_TOKEN", "IG_USER_ID", "IG_PAGE_TOKEN", "IG_PAGE_ID"):
        vault.delete_entry(n)
    store.put("ig/state", {})


def status(st: dict | None = None) -> dict:
    st = st if st is not None else state()
    on = connected(0) if st else False
    exp = st.get("expires_at") if st else None
    return {"connected": bool(on), "username": st.get("username") if st else None, "kind": st.get("kind") if st else None,
            "followers": st.get("followers") if st else None, "media_count": st.get("media_count") if st else None,
            "token_days_left": round((exp - time.time()) / 86400, 1) if exp else None, "settings": settings()}


def refresh_if_needed(force: bool = False) -> str:
    """Instagram-login tokens: refresh (another 60 days) when older than a day. Facebook-login user tokens: re-exchange with
    the app secret when < 15 days remain (needs IG_APP_ID + IG_APP_SECRET in the vault)."""
    st = state()
    if not st or not connected(0):
        return "not connected"
    tok, uid, kind = _client()
    now = time.time()
    exp = st.get("expires_at")
    if kind == "instagram":
        if not force and now - st.get("refreshed_at", 0) < 86400 * 5 and (not exp or exp - now > 20 * 86400):
            return "fresh"
        j = call("GET", "refresh_access_token", tok, {"grant_type": "ig_refresh_token"}, kind, raw_path=True)
    else:
        c = _creds()
        if not (c.get("IG_APP_ID") and c.get("IG_APP_SECRET")):
            return "no app secret (Facebook-login tokens from Graph Explorer expire; add IG_APP_ID/IG_APP_SECRET to refresh)"
        if not force and exp and exp - now > 15 * 86400:
            return "fresh"
        j = call("GET", "oauth/access_token", tok, {"grant_type": "fb_exchange_token", "client_id": c["IG_APP_ID"],
                                                    "client_secret": c["IG_APP_SECRET"], "fb_exchange_token": tok}, kind)
    new = j.get("access_token")
    if new:
        vault.set_entry("IG_ACCESS_TOKEN", new, f"Instagram token ({kind} login)")
        st.update(refreshed_at=now, expires_at=now + float(j.get("expires_in") or 60 * 86400))
        store.put("ig/state", st)
        return "refreshed"
    return "no token returned"


# ---------------------------------------------------------------- media hosting (Instagram fetches a public URL)
def host_image(data: bytes) -> str:
    """Store a JPEG (Instagram only accepts JPEG) privately and return a signed public URL served by /api/ig/m/."""
    from PIL import Image

    im = Image.open(io.BytesIO(data))
    im = im.convert("RGB")
    w, h = im.size
    r = w / h
    if r > 1.91 or r < 0.8:  # Instagram feed limits: 4:5 .. 1.91:1 -> pad to fit
        size = (w, -(-w * 100 // 191)) if r > 1.91 else (-(-h * 4 // 5), h)
        canvas = Image.new("RGB", size, (255, 255, 255))
        canvas.paste(im, ((size[0] - w) // 2, (size[1] - h) // 2))
        im = canvas
    if max(im.size) > 1440:
        s = 1440 / max(im.size)
        im = im.resize((int(im.width * s), int(im.height * s)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    name = f"{int(time.time())}-{secrets.token_hex(6)}.jpg"
    store.put_bytes(f"igmedia/{name}", buf.getvalue(), "image/jpeg")
    return media_url(name)


def media_url(name: str) -> str:
    return f"{PUBLIC_BASE}/api/ig/m/{name}?s={vault._hmac('igm|' + name)[:24]}"


def check_media_sig(name: str, sig: str) -> bool:
    import hmac as _h

    return bool(re.fullmatch(r"[0-9]+-[0-9a-f]{12}\.jpg", name or "")) and _h.compare_digest(sig or "", vault._hmac("igm|" + name)[:24])


# ---------------------------------------------------------------- publishing
def _wait_ready(cid: str, tok: str, kind: str, limit: float) -> None:
    t0 = time.time()
    while True:
        j = call("GET", cid, tok, {"fields": "status_code,status"}, kind)
        code = j.get("status_code", "FINISHED")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise IGError(f"Instagram could not process the media: {j.get('status', code)}")
        if time.time() - t0 > limit:
            raise IGError("Instagram is still processing the media; try publishing again in a minute")
        time.sleep(3)


def publish(caption: str, image_urls: list[str] | None = None, video_url: str = "", wait_limit: float = 90) -> dict:
    tok, uid, kind = _client()
    caption = (caption or "")[:2200]
    image_urls = [u for u in (image_urls or []) if u][:10]
    if video_url:
        c = call("POST", f"{uid}/media", tok, {"media_type": "REELS", "video_url": video_url, "caption": caption}, kind)
        _wait_ready(c["id"], tok, kind, max(wait_limit, 60))
        cid, mtype = c["id"], "REEL"
    elif len(image_urls) > 1:
        kids = [call("POST", f"{uid}/media", tok, {"image_url": u, "is_carousel_item": "true"}, kind)["id"] for u in image_urls]
        for k in kids:
            _wait_ready(k, tok, kind, 30)
        c = call("POST", f"{uid}/media", tok, {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption}, kind)
        _wait_ready(c["id"], tok, kind, 30)
        cid, mtype = c["id"], "CAROUSEL"
    elif image_urls:
        c = call("POST", f"{uid}/media", tok, {"image_url": image_urls[0], "caption": caption}, kind)
        _wait_ready(c["id"], tok, kind, 30)
        cid, mtype = c["id"], "IMAGE"
    else:
        raise IGError("a post needs at least one image or a video")
    pub = call("POST", f"{uid}/media_publish", tok, {"creation_id": cid}, kind)
    mid = pub.get("id", "")
    link = ""
    try:
        link = call("GET", mid, tok, {"fields": "permalink"}, kind).get("permalink", "")
    except IGError:
        pass
    log = store.get("ig/posts", [], max_age=60) or []
    log.append({"id": mid, "type": mtype, "permalink": link, "caption": caption[:200], "t": time.time()})
    store.put("ig/posts", log[-200:])
    return {"posted": True, "media_id": mid, "type": mtype, "permalink": link}


# ---------------------------------------------------------------- reading: media, comments, DMs, insights
def recent_media(limit: int = 10) -> list[dict]:
    tok, uid, kind = _client(3600)
    j = call("GET", f"{uid}/media", tok, {"fields": "id,caption,media_type,permalink,timestamp,like_count,comments_count",
                                           "limit": max(1, min(limit, 50))}, kind)
    return j.get("data", [])


def comments(media_id: str, limit: int = 50) -> list[dict]:
    tok, uid, kind = _client(3600)
    j = call("GET", f"{media_id}/comments", tok, {"fields": "id,text,username,timestamp,like_count,hidden,from,replies{id,text,username}",
                                                  "limit": limit}, kind)
    return j.get("data", [])


def reply(comment_id: str, message: str) -> dict:
    tok, uid, kind = _client(3600)
    return call("POST", f"{comment_id}/replies", tok, {"message": (message or "")[:2000]}, kind)


def hide(comment_id: str, hidden: bool = True) -> dict:
    tok, uid, kind = _client(3600)
    return call("POST", comment_id, tok, {"hide": "true" if hidden else "false"}, kind)


def dm_threads(limit: int = 15) -> list[dict]:
    """Instagram DMs (needs instagram_manage_messages / instagram_business_manage_messages). Best effort."""
    c = _creds(3600)
    tok, uid, kind = _client(3600)
    if kind == "facebook":
        page, ptok = c.get("IG_PAGE_ID", ""), c.get("IG_PAGE_TOKEN", "")
        if not (page and ptok):
            raise IGError("DMs need the Page token (reconnect with pages_show_list + instagram_manage_messages)")
        j = call("GET", f"{page}/conversations", ptok, {"platform": "instagram", "limit": limit,
                                                        "fields": "participants,updated_time,messages.limit(5){id,message,from,created_time}"}, kind)
    else:
        j = call("GET", "me/conversations", tok, {"platform": "instagram", "limit": limit,
                                                  "fields": "participants,updated_time,messages.limit(5){id,message,from,created_time}"}, kind)
    return j.get("data", [])


def insights(media_id: str = "") -> dict:
    tok, uid, kind = _client(3600)
    if media_id:
        out = {}
        for m in ("reach", "likes", "comments", "saved", "shares", "views", "total_interactions"):
            try:
                d = call("GET", f"{media_id}/insights", tok, {"metric": m}, kind).get("data", [])
                if d:
                    out[m] = (d[0].get("values") or [{}])[0].get("value", d[0].get("total_value", {}).get("value"))
            except IGError:
                continue
        return {"media_id": media_id, "metrics": out}
    prof = call("GET", uid, tok, {"fields": "username,followers_count,follows_count,media_count"}, kind)
    days = {}
    for m in ("reach", "profile_views", "accounts_engaged", "total_interactions", "follows_and_unfollows"):
        try:
            d = call("GET", f"{uid}/insights", tok, {"metric": m, "period": "day", "metric_type": "total_value"}, kind).get("data", [])
            if d:
                tv = d[0].get("total_value") or {}
                days[m] = tv.get("value", (d[0].get("values") or [{}])[-1].get("value"))
        except IGError:
            continue
    posts = []
    try:
        for p in recent_media(6):
            posts.append({"id": p.get("id"), "date": (p.get("timestamp") or "")[:10], "likes": p.get("like_count"),
                          "comments": p.get("comments_count"), "caption": (p.get("caption") or "")[:60], "link": p.get("permalink")})
    except IGError:
        pass
    st = state()
    if st:
        st.update(followers=prof.get("followers_count"), media_count=prof.get("media_count"))
        store.put("ig/state", st)
    return {"profile": prof, "today": days, "recent_posts": posts}


# ---------------------------------------------------------------- comment triage / leads
INTEREST_RE = re.compile(
    r"\b(price|pricing|cost|how much|interested|inbox|details?|service|hire|package|rates?|available|dm(?:'?d)?|"
    r"grow(?:th)?|followers?|engagement|book|order|quote|collab)\b|দাম|কত|প্রাইস|আগ্রহী|ইনবক্স|বিস্তারিত|সার্ভিস|নিতে চাই|"
    r"জানতে চাই|কিভাবে|কীভাবে|ফলোয়ার|গ্রো|প্যাকেজ|যোগাযোগ", re.I)
SPAM_RE = re.compile(
    r"(https?://|www\.|t\.me/|wa\.me/|bit\.ly|\.ly/)|follow ?back|check (my|our) (page|profile|bio)|crypto|bitcoin|forex|"
    r"earn \$|\$\d+ ?(per|a) day|investment|promo(te|tion)? (it )?on|dm (me|us) (for|to) (collab|promo|feature)|onlyfans|"
    r"sugar ?(daddy|mommy)|giveaway winner|send (it )?to @|cash ?app|💰💰|🔥{4,}", re.I)


def classify(text: str) -> str:
    t = text or ""
    if SPAM_RE.search(t):
        return "spam"
    if INTEREST_RE.search(t):
        return "lead"
    return "normal"


TEMPLATES = {
    "lead": {"bn": "ধন্যবাদ আগ্রহের জন্য! 🙌 বিস্তারিত জানতে আমাদের DM করুন, Md Zahngir Hossain নিজে আপনাকে সাহায্য করবেন।",
             "en": "Thanks for your interest! 🙌 Please DM us and Md Zahngir Hossain will help you personally."},
    "normal": {"bn": "ধন্যবাদ আপনার মন্তব্যের জন্য! ❤️", "en": "Thank you so much! ❤️"},
}


def has_bn(text: str) -> bool:
    return bool(re.search(r"[\u0980-\u09FF]", text or ""))


def template_reply(text: str, cls: str) -> str:
    return TEMPLATES["lead" if cls == "lead" else "normal"]["bn" if has_bn(text) else "en"]


def draft_reply(client, cfg, comment: str, username: str, post_caption: str = "", cls: str = "normal") -> str:
    """AI-written reply in the commenter's language; falls back to a safe template."""
    from sglbot import ai

    sys_p = ("You write short, warm Instagram comment replies for SocialGrowthLab (@socialgrowthlabhq), an organic Instagram/TikTok "
             "growth service run by Md Zahngir Hossain. Rules: reply in the commenter's language (Bengali or English), max 2 sentences, "
             "1 emoji max, no hashtags, never quote prices or guarantee results, never mention bots or automation. If they show "
             "interest in the service, thank them and invite them to send a DM (do NOT claim you already sent them anything). "
             "Output ONLY the reply text.")
    user = f"Post caption: {post_caption[:300]}\nComment by @{username}: {comment[:500]}\nType: {cls}"
    try:
        out = ai.complete(client, cfg, system_prompt=sys_p, history=[], user_message=user) or ""
        out = out.strip().strip('"').strip()
        if 2 <= len(out) <= 400:
            return out
    except Exception as exc:
        logger.warning("draft reply failed: %s", exc)
    return template_reply(comment, cls)


def add_lead(lead: dict) -> bool:
    """Store a lead once (by source id). Returns True if it is new."""
    leads = store.get("ig/leads", [], max_age=600) or []
    if any(x.get("id") == lead.get("id") for x in leads):
        return False
    leads.append({**lead, "t": time.time()})
    store.put("ig/leads", leads[-500:])
    return True


def leads(limit: int = 30) -> list[dict]:
    return (store.get("ig/leads", [], max_age=60) or [])[-limit:][::-1]


def new_comments(seen: set, media_limit: int = 6) -> list[dict]:
    """Unseen comments on the owner's recent posts (excluding the owner's own replies)."""
    st = state(3600)
    me = (st.get("username") or "").lower()
    out = []
    for m in recent_media(media_limit):
        if not m.get("comments_count"):
            continue
        for c in comments(m["id"]):
            if c["id"] in seen or (c.get("username") or "").lower() == me:
                continue
            out.append({**c, "media_id": m["id"], "permalink": m.get("permalink", ""), "caption": (m.get("caption") or "")[:300]})
    return out


def caption_for(client, cfg, theme: str, lang_bn: bool = False) -> str:
    from sglbot import ai

    sys_p = ("Write one Instagram post caption for SocialGrowthLab (@socialgrowthlabhq), an organic Instagram/TikTok growth service by "
             "Md Zahngir Hossain. Strong hook first line, 3-5 short lines of value, a call to action (DM / link in bio), then 8-15 relevant "
             "hashtags on the last line. No fake results, no prices. " + ("Write in Bengali." if lang_bn else "Write in English.") +
             " Output ONLY the caption.")
    return (ai.complete(client, cfg, system_prompt=sys_p, history=[], user_message=f"Post topic/theme: {theme}") or "").strip()[:2200]


def image_prompt_for(client, cfg, theme: str) -> str:
    from sglbot import ai

    sys_p = ("Write one English prompt for an AI image generator for an Instagram post visual (square). Modern, clean, eye-catching, "
             "brand colours purple/pink gradient accents, no text or letters in the image. Output ONLY the prompt (max 60 words).")
    return (ai.complete(client, cfg, system_prompt=sys_p, history=[], user_message=f"Post theme: {theme}") or theme).strip()[:600]
