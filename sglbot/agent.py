"""Nexora agent: the model picks tools (web search, reading links, lead finding, files, reminders, owner vault),
chains several calls, and answers in the user's language. Shared by the web app and the Telegram bot."""

from __future__ import annotations

import base64
import concurrent.futures as cf
import json
import logging
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from sglbot import ai, files, leadfinder, store, vault, websearch

logger = logging.getLogger(__name__)
BOT_USERNAME = "SocialGrowthLabAI_bot"


def _fn(name: str, desc: str, props: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required or []}}}


T_SEARCH = _fn("web_search",
               "Search the live web for current/latest information (news, prices, people, companies, events, anything after 2024 "
               "or anything you are not sure about). Returns numbered sources with snippets and page excerpts. Cite them.",
               {"query": {"type": "string", "description": "Search query (English usually works best; add the country/city if relevant)"},
                "news": {"type": "boolean", "description": "true for latest news/headlines"}}, ["query"])
T_READ = _fn("read_url", "Open a web page, PDF or YouTube video link and get its readable text/transcript to summarise or answer questions.",
             {"url": {"type": "string"}}, ["url"])
T_LEADS = _fn("find_leads",
              "Find potential clients/leads on the public web for a niche and location: businesses, websites, Instagram/TikTok/Facebook "
              "creators, with publicly listed email/phone. Produces a table plus downloadable CSV and Excel files.",
              {"niche": {"type": "string", "description": "e.g. 'bakery', 'fitness coach', 'real estate agency'"},
               "location": {"type": "string", "description": "city/country, e.g. 'Dhaka', 'London UK'"},
               "platform": {"type": "string", "enum": ["any", "website", "instagram", "tiktok", "facebook", "linkedin"]},
               "count": {"type": "integer", "description": "how many leads (max 40)"}}, ["niche"])
T_FILE = _fn("create_file",
             "Create a downloadable file for the user: pdf, docx (Word), xlsx (Excel), csv, txt or md. Bengali text is supported. "
             "Put the full document text in content (Markdown headings/bullets/tables ok) and/or tabular data in rows.",
             {"format": {"type": "string", "enum": ["pdf", "docx", "xlsx", "csv", "txt", "md"]},
              "title": {"type": "string"}, "content": {"type": "string"},
              "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
                       "description": "table rows; first row = header (for xlsx/csv or a table in pdf/docx)"}}, ["format", "title"])
T_REMIND = _fn("set_reminder",
               "Schedule a reminder or a recurring task delivered in Telegram. For a task (e.g. 'every morning send me 5 caption ideas') set task=true "
               "and put the instruction in message: Nexora will run it at that time and send the result.",
               {"message": {"type": "string", "description": "reminder text, or the instruction to run for a task"},
                "when": {"type": "string", "description": "local date-time ISO 8601 'YYYY-MM-DDTHH:MM' in the user's timezone (compute from the current time given in the system prompt)"},
                "repeat": {"type": "string", "enum": ["none", "daily", "weekdays", "weekly"]},
                "task": {"type": "boolean"}}, ["message", "when"])
T_LIST_REM = _fn("list_reminders", "List the user's active reminders and scheduled tasks.", {})
T_CANCEL_REM = _fn("cancel_reminder", "Cancel a reminder by its id (from list_reminders).", {"id": {"type": "string"}}, ["id"])
T_LINK = _fn("link_telegram", "Link this web chat to the user's Telegram using the code the Nexora Telegram bot gave them (/link).",
             {"code": {"type": "string"}}, ["code"])
T_VLIST = _fn("vault_list", "OWNER ONLY. List the names/notes of entries stored in the owner's encrypted vault (never values).", {})
T_VSAVE = _fn("vault_save", "OWNER ONLY. Save a login/API key/note in the encrypted vault (the value is never shown again).",
              {"name": {"type": "string", "description": "short id like OPENAI_KEY or IG_LOGIN"}, "value": {"type": "string"},
               "note": {"type": "string"}}, ["name", "value"])
T_VDEL = _fn("vault_delete", "OWNER ONLY. Delete a vault entry (consequential: ask the owner to confirm first).",
             {"name": {"type": "string"}}, ["name"])
T_HTTP = _fn("http_request",
             "OWNER ONLY. Call an external HTTP API on the owner's behalf. Use {{vault:NAME}} inside url/headers/body to insert a "
             "stored secret (never type secrets yourself). GET runs immediately; POST/PUT/PATCH/DELETE (posting, sending, deleting, "
             "buying...) first return CONFIRMATION_REQUIRED: describe the exact action to the owner, wait for their clear yes in the next "
             "message, then call again with exactly the same arguments.",
             {"method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]}, "url": {"type": "string"},
              "headers": {"type": "object", "additionalProperties": {"type": "string"}}, "body": {"type": "string"}}, ["method", "url"])

PUBLIC_TOOLS = [T_SEARCH, T_READ, T_LEADS, T_FILE, T_REMIND, T_LIST_REM, T_CANCEL_REM]
OWNER_TOOLS = [T_VLIST, T_VSAVE, T_VDEL, T_HTTP]
AGENT_TOOL_NAMES = {t["function"]["name"] for t in PUBLIC_TOOLS + OWNER_TOOLS + [T_LINK]}

LABELS = {
    "web_search": ("🔎 খুঁজছি", "🔎 Searching"), "read_url": ("📖 পড়ছি", "📖 Reading"),
    "find_leads": ("🧲 লিড খুঁজছি", "🧲 Finding leads"), "create_file": ("📄 ফাইল বানাচ্ছি", "📄 Creating file"),
    "set_reminder": ("⏰ রিমাইন্ডার সেট করছি", "⏰ Setting reminder"), "list_reminders": ("⏰ রিমাইন্ডার দেখছি", "⏰ Checking reminders"),
    "cancel_reminder": ("⏰ বাতিল করছি", "⏰ Cancelling"), "link_telegram": ("📲 Telegram লিংক করছি", "📲 Linking Telegram"),
    "vault_list": ("🔐 ভল্ট দেখছি", "🔐 Checking vault"), "vault_save": ("🔐 ভল্টে রাখছি", "🔐 Saving to vault"),
    "vault_delete": ("🔐 ভল্ট থেকে মুছছি", "🔐 Deleting from vault"), "http_request": ("🌐 API কল করছি", "🌐 Calling API"),
}


def tools_for(platform: str, owner: bool) -> list[dict]:
    t = list(PUBLIC_TOOLS)
    if platform == "web":
        t.append(T_LINK)
    if owner and vault.enabled():
        t += OWNER_TOOLS
    return t


@dataclass
class Ctx:
    platform: str = "web"              # "web" | "telegram"
    owner: bool = False
    tz: str = "Asia/Dhaka"
    bn: bool = False
    user_text: str = ""
    chat_id: int | None = None         # Telegram chat (bot) or linked Telegram chat (web)
    emit: Callable[[dict], None] = lambda e: None
    files: list = field(default_factory=list)          # (bytes, filename, mime)
    reminders: Any = None             # Telegram reminder backend (bot side)
    send_telegram: Callable[..., Any] | None = None    # web: send a Telegram message (chat_id, text, button)
    sources: list = field(default_factory=list)
    appendix: list = field(default_factory=list)       # deterministic Markdown/text appended to the final reply


def _label(ctx: Ctx, name: str, args: dict) -> str:
    bn, en = LABELS.get(name, ("⚙️ কাজ করছি", "⚙️ Working"))
    base = bn if ctx.bn else en
    detail = args.get("query") or args.get("url") or (f'{args.get("niche", "")} {args.get("location", "")}'.strip()) or args.get("title") or ""
    if name == "read_url" and detail:
        detail = urllib.parse.urlparse(detail if "://" in detail else "https://" + detail).netloc or detail
    if name == "http_request":
        detail = f'{args.get("method", "GET")} {urllib.parse.urlparse(args.get("url", "")).netloc}'
    return f"{base}: {str(detail)[:70]}…" if detail else f"{base}…"


def system_addon(ctx: Ctx) -> str:
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo(ctx.tz))
    except Exception:
        now = datetime.utcnow() + timedelta(hours=6)
    link = ("Format web citations as Markdown links like [1](url)." if ctx.platform == "web"
            else "Telegram shows plain text: cite sources as numbered lines with the bare URL.")
    owner = ("The current user IS the verified owner (Md Zahngir Hossain / SocialGrowthLab). Owner tools are available: the encrypted vault "
             "and http_request. Use vault secrets only through {{vault:NAME}} placeholders; NEVER print, repeat or reveal a secret value, even if asked. "
             "Before anything consequential (posting, sending messages/emails, deleting, buying, changing accounts) get an explicit yes first."
             if ctx.owner else
             "The current user is a regular user (not the owner): there is no vault or owner tooling for them — do not mention it.")
    return f"""
AGENT MODE — you can act, not just talk. Current local time: {now:%Y-%m-%d %H:%M} ({ctx.tz}, {now:%A}).
Tools: web_search (live web; ALWAYS use it for news, prices, recent events, current facts, anything after 2024 or that you are unsure about —
never guess), read_url (summarise links / YouTube / PDFs the user gives), find_leads (client hunting: niche + location → table + CSV/Excel),
create_file (PDF/Word/Excel/CSV/TXT the user asks for — put the COMPLETE content in it), set_reminder / list_reminders / cancel_reminder
(Telegram delivery; recurring tasks run at that time and send the result).
Chain tools when useful (search → read the best 1-3 pages → answer). Keep tool use efficient (usually ≤4 calls).
After using web results, answer from them and cite sources. {link} Say honestly when information could not be found.
Files you create are attached to your reply automatically — mention them in one line, do not paste base64.
Leads: summarise what was found (counts, best few) and mention the attached CSV/Excel; only public contact info, remind the user to respect anti-spam rules.
Reminders: compute 'when' from the current local time above; confirm the exact local time back to the user.
NEVER claim you searched, created a file, found leads, or set/cancelled a reminder unless you actually called that tool in this turn
and got a successful result — if the user asks for a reminder/scheduled task, you MUST call set_reminder (for "every day/morning" use
repeat=daily; for "send me X every morning" use task=true).
{owner}
"""


# ---------------------------------------------------------------- time parsing
def parse_when(when: str, tz: str, repeat: str = "none") -> datetime:
    from zoneinfo import ZoneInfo

    z = ZoneInfo(tz or "Asia/Dhaka")
    now = datetime.now(z)
    s = (when or "").strip()
    m = re.match(r"^in\s+(\d+)\s*(min|minute|minutes|m|hour|hours|h|day|days|d)$", s, re.I)
    if m:
        n, u = int(m.group(1)), m.group(2).lower()[0]
        return now + {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[u]
    if re.match(r"^\d{1,2}:\d{2}$", s):
        h, mi = map(int, s.split(":"))
        dt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    else:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        dt = dt.replace(tzinfo=z) if dt.tzinfo is None else dt.astimezone(z)
    if dt <= now + timedelta(seconds=20):
        if repeat in ("daily", "weekdays", "weekly"):
            while dt <= now:
                dt += timedelta(days=7 if repeat == "weekly" else 1)
        else:
            raise ValueError("that time is already in the past")
    return dt


# ---------------------------------------------------------------- tools
def _t_search(ctx: Ctx, a: dict) -> dict:
    q = (a.get("query") or "").strip()
    res = websearch.news(q, 8, "bn" if ctx.bn else "en") if a.get("news") else []
    if not res:
        res = websearch.search(q, 8)
    if a.get("news") and len(res) < 3:
        res += websearch.search(q, 6)
    out = []
    for r in res[:8]:
        ctx.sources.append(r["url"])
        out.append({"n": len(ctx.sources), "title": r["title"], "url": r["url"], "snippet": r.get("snippet", "")})
    # Read the top pages so the answer is grounded (time-boxed).
    top = [o["url"] for o in out if "news.google.com" not in o["url"]][:3]
    pages = websearch.read_many(top, max_chars=2500, workers=3, timeout=14) if top else []
    by = {p.get("src"): p for p in pages}
    for o in out:
        p = by.get(o["url"])
        if p and p.get("text"):
            o["excerpt"] = p["text"][:2500]
    cite = "cite inline as [n](url)" if ctx.platform == "web" else "cite as [n] and list 'n. url' at the end"
    return {"query": q, "results": out, "how_to_cite": cite} if out else {"query": q, "results": [], "note": "no results (search engines unavailable)"}


def _t_read(ctx: Ctx, a: dict) -> dict:
    r = websearch.read_url(a.get("url", ""), max_chars=24000)
    if r.get("url"):
        ctx.sources.append(r["url"])
    return r


def _t_leads(ctx: Ctx, a: dict) -> dict:
    count = max(5, min(40, int(a.get("count") or 20)))
    r = leadfinder.find_leads(a.get("niche", ""), a.get("location", ""), a.get("platform") or "any", count)
    rows = r["rows"]
    title = f'leads-{a.get("niche", "")}-{a.get("location", "")}'.strip("-")
    if len(rows) > 1:
        for fmt in ("xlsx", "csv"):
            data, name, mime = files.make_file(fmt, title, rows=[[str(c) for c in row] for row in rows])
            _attach(ctx, data, name, mime)
    ctx.appendix.append(_leads_md(rows, ctx.platform))
    names = [row[1] for row in rows[1:9]]
    return {"found": r["count"], "with_public_email": r["with_email"], "sample_names": names,
            "files": "CSV + Excel ALREADY attached — do not create another file" if len(rows) > 1 else "none",
            "IMPORTANT": "The full real table is shown to the user automatically under your reply. Do NOT write a table or any "
                         "names/emails/phones yourself (never invent contact details). Just give a short summary (how many, how many "
                         "with public email), 2-3 outreach tips, and mention the attached Excel/CSV."}


def _leads_md(rows: list[list], platform: str) -> str:
    def cell(v):
        return str(v or "—").replace("|", "/").replace("\n", " ")[:60]
    body = rows[1:]
    if not body:
        return ""
    if platform == "web":
        icon = {"Instagram": "📸", "TikTok": "🎵", "Facebook": "📘", "LinkedIn": "💼", "YouTube": "▶️", "X": "𝕏"}
        out = ["| # | Name / link | Email · Phone |", "|---|---|---|"]
        for row in body:
            label = cell(row[3] or urllib.parse.urlparse(row[4]).netloc.removeprefix("www."))
            link = f"{icon.get(row[2], '🌐')} [{label}]({row[4]})" if row[4] else ""
            contact = " · ".join(cell(x) for x in (row[5], row[6]) if x) or "—"
            out.append(f"| {row[0]} | **{cell(row[1])[:48]}**<br>{link} | {contact} |")
        return "\n".join(out)
    out = []
    for row in body:
        extra = " · ".join(x for x in (row[5], row[6]) if x)
        out.append(f"{row[0]}. {row[1]} ({row[2]}) — {row[4]}" + (f"\n   {extra}" if extra else ""))
    return "\n".join(out)


def _attach(ctx: Ctx, data: bytes, name: str, mime: str) -> None:
    ctx.files.append((data, name, mime))
    ctx.emit({"file": {"name": name, "mime": mime, "size": len(data),
                       "data": base64.b64encode(data).decode() if ctx.platform == "web" else ""}})


def _t_file(ctx: Ctx, a: dict) -> dict:
    data, name, mime = files.make_file(a.get("format", "pdf"), a.get("title", "Nexora"), a.get("content", ""), a.get("rows") or None)
    _attach(ctx, data, name, mime)
    return {"created": name, "bytes": len(data)}


def _rem_spec(ctx: Ctx, a: dict) -> dict:
    repeat = a.get("repeat") or "none"
    dt = parse_when(a.get("when", ""), ctx.tz, repeat)
    return {"id": secrets.token_hex(4), "text": (a.get("message") or "").strip()[:1500], "task": bool(a.get("task")),
            "repeat": repeat, "tz": ctx.tz, "at": dt.isoformat(), "created": time.time(),
            "lang": "bn" if ctx.bn else "en"}


def _t_remind(ctx: Ctx, a: dict) -> dict:
    spec = _rem_spec(ctx, a)
    if ctx.platform == "telegram" and ctx.reminders is not None:
        ctx.reminders.add(ctx.chat_id, spec)
        return {"scheduled": True, "local_time": spec["at"], "repeat": spec["repeat"], "id": spec["id"]}
    # Web: hand it to the Telegram bot (it runs the schedule on the box with persistent storage).
    store.put(f"reminders/pending/{spec['id']}", spec)
    start = f"https://t.me/{BOT_USERNAME}?start=r_{spec['id']}"
    if ctx.chat_id and ctx.send_telegram:
        ok = ctx.send_telegram(ctx.chat_id, spec)
        if ok:
            return {"status": "sent to the user's linked Telegram — they must tap ✅ Activate there once", "local_time": spec["at"],
                    "repeat": spec["repeat"]}
    ctx.emit({"link": {"url": start, "label": "⏰ Telegram-এ চালু করুন" if ctx.bn else "⏰ Activate in Telegram"}})
    return {"status": "needs Telegram: tell the user to tap the 'Activate in Telegram' button (opens the Nexora bot, then Start). "
                      "Reminders are delivered in Telegram.", "local_time": spec["at"], "repeat": spec["repeat"], "link": start}


def _t_list_rem(ctx: Ctx, a: dict) -> dict:
    if ctx.platform == "telegram" and ctx.reminders is not None:
        return {"reminders": ctx.reminders.list(ctx.chat_id)}
    return {"note": "Reminders live in Telegram: send /reminders to the Nexora bot to see or cancel them.",
            "bot": f"https://t.me/{BOT_USERNAME}"}


def _t_cancel_rem(ctx: Ctx, a: dict) -> dict:
    if ctx.platform == "telegram" and ctx.reminders is not None:
        return {"cancelled": ctx.reminders.cancel(ctx.chat_id, str(a.get("id", "")))}
    return {"note": "Cancel it in Telegram with /reminders."}


def _t_link(ctx: Ctx, a: dict) -> dict:
    cid = vault.parse_link_code(a.get("code", ""))
    if not cid:
        return {"error": "invalid code — send /link to the Nexora Telegram bot to get a fresh code"}
    ctx.chat_id = cid
    ctx.emit({"tg_link": vault.link_token(cid)})
    return {"linked": True}


# ---- owner
def _need_owner(ctx: Ctx):
    if not ctx.owner:
        raise PermissionError("owner only")


def _ut(ctx: Ctx) -> str:
    import hashlib

    return hashlib.sha256((ctx.user_text or str(time.time())).encode()).hexdigest()[:16]


def _confirmed(ctx: Ctx, kind: str, payload: dict, confirm_id: str | None) -> tuple[bool, dict | None]:
    """Consequential owner actions need a clear 'yes' from the owner in a LATER message than the one that proposed them."""
    import hashlib

    sig = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    cid = hashlib.sha256(sig.encode()).hexdigest()[:16]
    key = f"agent/pending/{cid}"
    rec = store.get(key, None) or {}
    fresh = time.time() - rec.get("t", 0) < 1800
    earlier = fresh and rec.get("ut") and rec.get("ut") != _ut(ctx)
    text = ctx.user_text or ""
    yes = re.search(r"\b(yes|yeah|yep|ok|okay|sure|confirm|go ahead|do it|proceed)\b|হ্যাঁ|হ্যা|জি|ঠিক আছে|করো|করুন|চালাও|পাঠাও|দাও", text, re.I)
    no = re.search(r"\b(no|don't|dont|cancel|stop)\b|না\b|বাতিল|থামো", text, re.I)
    if earlier and yes and not no:
        store.put(key, {"t": 0, "done": time.time()})
        return True, None
    if earlier and not yes:
        store.put(key, {"t": 0})
        return False, {"status": "NOT confirmed — the owner did not clearly say yes. Do not do it; ask what they want instead."}
    if not fresh:
        store.put(key, {"sig": sig, "kind": kind, "t": time.time(), "ut": _ut(ctx)})
    return False, {"status": "CONFIRMATION_REQUIRED",
                   "instruction": "Do NOT retry now. Describe exactly what will happen (method, target, key content) and ask the owner "
                                  "to reply yes. After their yes (next message), call again with the same arguments."}


def _t_vlist(ctx: Ctx, a: dict) -> dict:
    _need_owner(ctx)
    return {"entries": vault.list_entries()}


def _t_vsave(ctx: Ctx, a: dict) -> dict:
    _need_owner(ctx)
    vault.set_entry(a.get("name", ""), a.get("value", ""), a.get("note", ""))
    return {"saved": a.get("name"), "note": "stored encrypted; never repeat the value"}


def _t_vdel(ctx: Ctx, a: dict) -> dict:
    _need_owner(ctx)
    ok, info = _confirmed(ctx, "vault_delete", {"name": a.get("name")}, None)
    if not ok:
        return info
    return {"deleted": vault.delete_entry(a.get("name", ""))}


_PRIVATE = re.compile(r"^(localhost|127\.|10\.|192\.168\.|169\.254\.|0\.|172\.(1[6-9]|2\d|3[01])\.)|\.internal$|\.local$", re.I)


def _t_http(ctx: Ctx, a: dict) -> dict:
    _need_owner(ctx)
    method = (a.get("method") or "GET").upper()
    url, headers, body = a.get("url", ""), dict(a.get("headers") or {}), a.get("body") or ""
    host = urllib.parse.urlparse(url).hostname or ""
    if not url.startswith("https://") or _PRIVATE.search(host):
        return {"error": "only public https URLs are allowed"}
    if method != "GET":
        ok, info = _confirmed(ctx, "http", {"m": method, "u": url, "h": headers, "b": body}, None)
        if not ok:
            return info
    used = []

    def sub(s: str) -> str:
        def rep(m):
            used.append(m.group(1))
            return vault.get_value(m.group(1))
        return re.sub(r"\{\{\s*vault:([A-Za-z0-9_.-]+)\s*\}\}", rep, s)

    url2 = sub(url)
    headers2 = {k: sub(str(v)) for k, v in headers.items()}
    body2 = sub(body).encode() if body else None
    if body2 and not any(k.lower() == "content-type" for k in headers2):
        headers2["Content-Type"] = "application/json" if body.strip().startswith(("{", "[")) else "text/plain"
    req = urllib.request.Request(url2, data=body2, method=method, headers={"User-Agent": "NexoraAI-Agent/1.0", **headers2})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            st, text = r.status, r.read(200_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        st, text = e.code, (e.read(50_000) or b"").decode("utf-8", "ignore")
    secrets_used = [vault.get_value(n) for n in used]
    return {"status": st, "body": vault.redact(text[:6000], secrets_used + vault.secret_values())}


HANDLERS = {"web_search": _t_search, "read_url": _t_read, "find_leads": _t_leads, "create_file": _t_file,
            "set_reminder": _t_remind, "list_reminders": _t_list_rem, "cancel_reminder": _t_cancel_rem, "link_telegram": _t_link,
            "vault_list": _t_vlist, "vault_save": _t_vsave, "vault_delete": _t_vdel, "http_request": _t_http}
TIMEOUTS = {"find_leads": 60, "web_search": 40, "read_url": 30, "http_request": 30}


def run_tool(ctx: Ctx, name: str, args: dict) -> str:
    fn = HANDLERS.get(name)
    if not fn:
        return json.dumps({"error": f"unknown tool {name}"})
    if name in ("vault_list", "vault_save", "vault_delete", "http_request") and not ctx.owner:
        return json.dumps({"error": "not available"})
    ctx.emit({"tool": {"name": name, "label": _label(ctx, name, args)}})
    t0 = time.time()
    try:
        ex = cf.ThreadPoolExecutor(max_workers=1)
        try:
            res = ex.submit(fn, ctx, args).result(timeout=TIMEOUTS.get(name, 30))
        finally:
            ex.shutdown(wait=False)
    except cf.TimeoutError:
        res = {"error": "timed out"}
    except (PermissionError, vault.VaultError, ValueError) as exc:
        res = {"error": str(exc)}
    except Exception as exc:
        logger.exception("tool %s failed", name)
        res = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    logger.info("tool %s done in %.1fs", name, time.time() - t0)
    text = json.dumps(res, ensure_ascii=False, default=str)
    if ctx.owner and name in ("http_request", "vault_list"):
        text = vault.redact(text)
    return text[:16000]


# ---------------------------------------------------------------- loop
def cite_links(text: str, ctx: Ctx) -> str:
    """[n] → clickable source links (web) / keep numbers (Telegram); drop stray [n] when nothing was searched."""
    if not ctx.sources:
        return re.sub(r"\s?\[(\d{1,2})\](?!\()", "", text)
    if ctx.platform != "web":
        return text

    def rep(m):
        n = int(m.group(1))
        return f"[[{n}]]({ctx.sources[n - 1]})" if 0 < n <= len(ctx.sources) else ""
    return re.sub(r"\[(\d{1,2})\](?!\()", rep, text)



_INTENTS = [
    ("set_reminder", re.compile(r"\bremind(er)?s?\b|\bremember to\b|মনে করিয়ে|মনে করাবে|মনে করাই|রিমাইন্ডার|অ্যালার্ম|\balarm\b|"
                                r"(every|each) (day|morning|evening|night|week|monday|sunday)|প্রতিদিন .*(পাঠা|দিও|দেবে|দিবে)|প্রতি (সকালে|রাতে|সপ্তাহে)", re.I)),
    ("find_leads", re.compile(r"\bleads?\b|লিড|\bclients?\b.*\b(find|list|get)\b|\b(find|get|list)\b.*\bclients?\b|ক্লায়েন্ট.*(খুঁজ|বের|লিস্ট)|prospects?", re.I)),
    ("create_file", re.compile(r"\b(pdf|docx|word file|word doc|excel|xlsx|spreadsheet|csv)\b|পিডিএফ|এক্সেল|ওয়ার্ড ফাইল|স্প্রেডশিট", re.I)),
    ("read_url", re.compile(r"https?://\S+", re.I)),
]


def forced_tool(text: str, tools: list[dict]) -> str | None:
    """Tool the user clearly asked for (the model sometimes answers 'done!' without calling it)."""
    names = {t["function"]["name"] for t in tools}
    t = (text or "")[-1500:]
    if "[Attached file:" in (text or "")[:20]:
        t = t.split("[User message]")[-1]
    for name, rx in _INTENTS:
        if name in names and rx.search(t):
            if name == "find_leads" and re.search(r"\b(what|how|explain|কী|কিভাবে)\b", t, re.I) and not re.search(r"খুঁজ|find|list|বের", t, re.I):
                continue
            if name == "create_file" and not re.search(r"\b(make|create|generate|give|export|prepare|build|send)\b|বানা|তৈরি|দাও|দিন|দিবে|দেবে|করে দাও", t, re.I):
                continue
            if name == "find_leads" and not re.search(r"\b(find|get|list|search|give|collect|need)\b|খুঁজ|বের|লিস্ট|দাও|তালিকা|চাই", t, re.I):
                continue
            return name
    return None


def run(client, cfg, messages: list[dict], ctx: Ctx, tools: list[dict] | None = None,
        on_extra: Callable[[str, dict], str | dict | None] | None = None, max_rounds: int = 7,
        first_tool: str | None = None) -> str | dict:
    """Non-streaming agent loop. Returns the final text, or a dict action from on_extra (e.g. image generation)."""
    tools = tools if tools is not None else tools_for(ctx.platform, ctx.owner)
    msgs = list(messages)
    chain = ai.model_chain(cfg)
    mi = 0
    for rnd in range(max_rounds):
        resp = None
        last_exc = None
        for attempt in range(len(chain) + 2):
            model = chain[min(mi, len(chain) - 1)]
            last = mi >= len(chain) - 1
            try:
                kw = dict(model=model, messages=msgs, temperature=0.4)
                if tools and rnd < max_rounds - 1:
                    kw.update(tools=tools, tool_choice="auto")
                    if rnd == 0 and first_tool:
                        kw["tool_choice"] = {"type": "function", "function": {"name": first_tool}}
                resp = ai.fast_client(client, last).chat.completions.create(**kw)
                break
            except Exception as exc:
                last_exc = exc
                if not last and ai.should_fallback(exc):
                    ai.mark_failed(model, exc); mi += 1; continue
                if last and attempt < len(chain) + 1:
                    time.sleep(1.5); continue
                raise
        if resp is None:
            raise last_exc or RuntimeError("no response")
        msg = resp.choices[0].message
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            return cite_links((msg.content or "").strip(), ctx)
        msgs.append({"role": "assistant", "content": msg.content or None, "tool_calls": [ai._tool_call_dict(c) for c in calls]})
        for c in calls:
            name = c.function.name
            try:
                args = json.loads(c.function.arguments or "{}") or {}
            except Exception:
                args = {}
            if name in HANDLERS:
                out = run_tool(ctx, name, args)
            elif on_extra:
                r = on_extra(name, args)
                if isinstance(r, dict) and r.get("__stop__"):
                    return r["__stop__"]
                out = r if isinstance(r, str) else json.dumps(r or {"ok": True})
            else:
                out = json.dumps({"error": "unknown tool"})
            msgs.append({"role": "tool", "tool_call_id": c.id, "content": out})
    return ""
