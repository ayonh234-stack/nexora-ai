"""Ready-made specialist agents and owner/user custom agents for Nexora."""

from __future__ import annotations

import re
import time
from typing import Any

from sglbot import store

ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,32}$")
MAX_CUSTOM = 24
MAX_INSTRUCTIONS = 4000

# Tool group names used by the UI and stored on each agent. Expanded in agent.tools_for.
TOOL_GROUPS = ("web", "image", "video", "files", "leads", "reminders", "computer")

PRESETS: list[dict[str, Any]] = [
    {
        "id": "ig-writer",
        "emoji": "📸",
        "name_bn": "ইনস্টা কনটেন্ট",
        "name_en": "Instagram writer",
        "blurb_bn": "ক্যাপশন, হুক, ক্যারোসেল ও রিল স্ক্রিপ্ট",
        "blurb_en": "Captions, hooks, carousels and reel scripts",
        "tools": ["image", "web", "files"],
        "instructions": (
            "You are Nexora's Instagram content writer for small businesses and creators. "
            "Write hooks, captions, carousel outlines and short reel scripts. Default to the user's language "
            "(Bengali or English). Keep captions scannable with short lines, a clear hook in the first line, "
            "a soft CTA, and 3–8 relevant hashtags. Offer 2–3 variants when useful. "
            "If a visual would help, call generate_image with a detailed English prompt (do not mention fallback servers). "
            "Do not invent engagement numbers. Stay on-brand, warm and specific — never generic 'hustle' spam."
        ),
    },
    {
        "id": "lead-finder",
        "emoji": "🧲",
        "name_bn": "লিড খোঁজা",
        "name_en": "Lead finder",
        "blurb_bn": "নিশ ও এলাকা ধরে সম্ভাব্য ক্লায়েন্ট খুঁজে এক্সেল দেয়",
        "blurb_en": "Find potential clients for a niche and export Excel",
        "tools": ["web", "leads", "files"],
        "instructions": (
            "You are Nexora's lead-finding specialist. When the user names a niche and (ideally) a city or country, "
            "you MUST call find_leads. Summarise how many were found, highlight the best few, and mention the attached "
            "CSV/Excel. Only use publicly listed contact details. Remind the user to follow anti-spam rules and to "
            "personalise outreach. If location or niche is missing, ask one short question, then search."
        ),
    },
    {
        "id": "sales-dm",
        "emoji": "💬",
        "name_bn": "সেলস DM",
        "name_en": "Sales DM writer",
        "blurb_bn": "ইনস্টা/হোয়াটসঅ্যাপ-এর ছোট, মানবিক মেসেজ",
        "blurb_en": "Short, human Instagram and WhatsApp messages",
        "tools": ["web"],
        "instructions": (
            "You are Nexora's sales-DM writer. Draft short, human first messages, follow-ups and soft closes for "
            "Instagram, WhatsApp or Telegram. 2–4 sentences, no walls of text, no fake urgency, no 'I came across your profile "
            "and I love your work' templates. Offer 2–3 variants (casual / professional). Write in the user's language. "
            "If you don't know the recipient's niche, ask one question first. Never claim you sent a message — you only draft it."
        ),
    },
    {
        "id": "researcher",
        "emoji": "🔎",
        "name_bn": "রিসার্চ",
        "name_en": "Researcher",
        "blurb_bn": "ওয়েব খুঁজে সূত্রসহ সংক্ষিপ্ত রিপোর্ট",
        "blurb_en": "Live web research with sources and a short brief",
        "tools": ["web", "files", "computer"],
        "instructions": (
            "You are Nexora's researcher. For anything current or factual you MUST use web_search, then read_url on the "
            "best 1–3 sources before answering. Cite sources. Be concise: start with the answer, then key facts, then caveats. "
            "If the user wants a document, create a PDF or Word brief with create_file. Never invent citations or numbers. "
            "If the virtual computer is available and a live screenshot or a small script would help, use it."
        ),
    },
    {
        "id": "coder",
        "emoji": "💻",
        "name_bn": "কোডার",
        "name_en": "Coder",
        "blurb_bn": "পাইথন লিখে চালায়, স্ক্রিপ্ট ও ফাইল বানায়",
        "blurb_en": "Writes and runs Python, builds scripts and files",
        "tools": ["computer", "files", "web"],
        "instructions": (
            "You are Nexora's coder. Prefer Python. When the virtual computer is available, actually run code with "
            "run_python rather than only showing it — then explain the result briefly. Keep programs short and self-contained. "
            "Do not try to read secrets, .env files or other users' data. If a downloadable script or document is useful, "
            "create it with create_file or computer_file. If the computer is offline, say so and still provide the code."
        ),
    },
    {
        "id": "copywriter",
        "emoji": "✍️",
        "name_bn": "কপিরাইটার",
        "name_en": "Copywriter",
        "blurb_bn": "অ্যাড, ল্যান্ডিং পেজ, ইমেইল ও পোস্টের কপি",
        "blurb_en": "Ads, landing pages, emails and post copy",
        "tools": ["web", "files", "image"],
        "instructions": (
            "You are Nexora's copywriter. Write ads, landing-page sections, email sequences and social posts in the user's "
            "language. Be concrete, benefit-led and easy to scan. Offer a headline plus 2 variants when useful. "
            "Do not overpromise results. If a visual is requested, generate an image. If they want a leave-behind, create a file."
        ),
    },
]


def public_view(agent: dict, bn: bool = True) -> dict:
    return {
        "id": agent["id"],
        "emoji": agent.get("emoji") or "🤖",
        "name": agent.get("name_bn") if bn else agent.get("name_en") or agent.get("name_bn"),
        "name_bn": agent.get("name_bn") or agent.get("name") or "",
        "name_en": agent.get("name_en") or agent.get("name") or "",
        "blurb": agent.get("blurb_bn") if bn else agent.get("blurb_en") or agent.get("blurb_bn") or "",
        "tools": list(agent.get("tools") or []),
        "builtin": not agent.get("custom"),
        "custom": bool(agent.get("custom")),
        "instructions": (agent.get("instructions") or "")[:MAX_INSTRUCTIONS],
    }


def presets(bn: bool = True) -> list[dict]:
    return [public_view(a, bn) for a in PRESETS]


def _custom() -> list[dict]:
    raw = store.get("agents/owner", None, max_age=5) or []
    if not isinstance(raw, list):
        return []
    return [a for a in raw if isinstance(a, dict) and ID_RE.match(str(a.get("id") or ""))]


def list_all(owner: bool, bn: bool = True) -> list[dict]:
    out = presets(bn)
    if owner:
        out.extend(public_view(a, bn) for a in _custom())
    return out


def get(agent_id: str, owner: bool = False) -> dict | None:
    aid = (agent_id or "").strip()
    for a in PRESETS:
        if a["id"] == aid:
            return dict(a)
    if owner:
        for a in _custom():
            if a.get("id") == aid:
                return dict(a)
    return None


def _clean_tools(tools) -> list[str]:
    allowed = set(TOOL_GROUPS)
    out = []
    for t in tools or []:
        name = str(t).strip().lower()
        if name in allowed and name not in out:
            out.append(name)
    return out or ["web"]


def _clean_id(raw: str, custom: bool = True) -> str:
    s = re.sub(r"[^a-z0-9-]", "", (raw or "").strip().lower())[:32]
    if custom and not s.startswith("c-"):
        s = "c-" + (s or time.strftime("%y%m%d%H%M%S"))
    if not ID_RE.match(s):
        raise ValueError("invalid id")
    if any(p["id"] == s for p in PRESETS):
        raise ValueError("that id is reserved")
    return s


def save_custom(body: dict) -> dict:
    emoji = (body.get("emoji") or "🤖").strip()[:4] or "🤖"
    name_bn = (body.get("name_bn") or body.get("name") or "").strip()[:40]
    name_en = (body.get("name_en") or body.get("name") or name_bn).strip()[:40]
    if not name_bn:
        raise ValueError("name required")
    instructions = (body.get("instructions") or "").strip()[:MAX_INSTRUCTIONS]
    if len(instructions) < 8:
        raise ValueError("instructions too short")
    tools = _clean_tools(body.get("tools"))
    existing = _custom()
    aid = (body.get("id") or "").strip()
    if aid:
        aid = _clean_id(aid)
        existing = [a for a in existing if a.get("id") != aid]
    else:
        base = re.sub(r"[^a-z0-9]+", "-", name_en.lower()).strip("-")[:20] or "agent"
        aid = _clean_id(base)
        n, candidate = 2, aid
        have = {a["id"] for a in existing}
        while candidate in have:
            candidate = _clean_id(f"{base}{n}")
            n += 1
        aid = candidate
    if len(existing) >= MAX_CUSTOM:
        raise ValueError("too many custom agents")
    rec = {
        "id": aid, "emoji": emoji, "name_bn": name_bn, "name_en": name_en,
        "blurb_bn": (body.get("blurb_bn") or body.get("blurb") or "")[:80],
        "blurb_en": (body.get("blurb_en") or body.get("blurb") or "")[:80],
        "tools": tools, "instructions": instructions, "custom": True, "updated": time.time(),
    }
    existing.append(rec)
    store.put("agents/owner", existing)
    return rec


def delete_custom(agent_id: str) -> None:
    aid = (agent_id or "").strip()
    if any(p["id"] == aid for p in PRESETS):
        raise ValueError("cannot delete a built-in agent")
    store.put("agents/owner", [a for a in _custom() if a.get("id") != aid])


def sanitize_client_agent(raw: dict | None, owner: bool) -> dict | None:
    """Accept a localStorage custom agent for this turn only. Never grants owner-only tool groups to a guest."""
    if not isinstance(raw, dict):
        return None
    name = (raw.get("name_bn") or raw.get("name") or raw.get("name_en") or "").strip()[:40]
    instructions = (raw.get("instructions") or "").strip()[:MAX_INSTRUCTIONS]
    if not name or len(instructions) < 8:
        return None
    tools = _clean_tools(raw.get("tools"))
    if not owner:
        tools = [t for t in tools if t != "computer"]
    return {
        "id": "local",
        "emoji": (raw.get("emoji") or "🤖")[:4],
        "name_bn": name,
        "name_en": (raw.get("name_en") or name)[:40],
        "tools": tools,
        "instructions": instructions,
        "custom": True,
    }


def addon(agent: dict) -> str:
    name = agent.get("name_en") or agent.get("name_bn") or "specialist"
    return (
        f"\nSPECIALIST AGENT: you are currently the '{agent.get('emoji', '')} {name}' agent. "
        f"Stay in this role for the whole turn.\n{agent.get('instructions') or ''}\n"
        f"Enabled tool groups for this agent: {', '.join(agent.get('tools') or []) or 'none (conversation only)'}. "
        "Do not claim you used a tool that is not enabled."
    )
