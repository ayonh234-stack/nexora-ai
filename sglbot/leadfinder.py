"""Find potential clients/leads on the public web (free): businesses, websites and IG/TikTok/Facebook creators
for a niche + location. Only publicly listed contact details are collected."""

from __future__ import annotations

import concurrent.futures as cf
import logging
import re
import time
import urllib.parse

from sglbot import websearch

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
PHONE_RE = re.compile(r"(?:\+?880[\s-]?1[3-9]\d{2}[\s-]?\d{6}|\b01[3-9]\d{2}[\s-]?\d{6}\b|\+\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4})")
BAD_EMAIL = re.compile(r"(\.(png|jpe?g|gif|webp|svg|css|js)$|example\.|sentry|wixpress|domain\.com|email\.com|yourname|@2x|u00)", re.I)
SOCIAL = {"instagram.com": "Instagram", "tiktok.com": "TikTok", "facebook.com": "Facebook", "linkedin.com": "LinkedIn",
          "youtube.com": "YouTube", "x.com": "X", "twitter.com": "X"}
DIRECTORIES = ("sortlist.", "clutch.co", "yelp.", "tripadvisor.", "justdial.", "wikipedia.", "glassdoor.", "indeed.",
               "upwork.", "fiverr.", "goodfirms.", "designrush.", "themanifest.", "quora.", "reddit.", "medium.com",
               "bdjobs.", "pinterest.", "google.", "bing.", "duckduckgo.", "foodpanda.", "daraz.", "amazon.")


def _platform(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    for dom, name in SOCIAL.items():
        if host == dom or host.endswith("." + dom):
            return name
    return "Website"


def _handle(url: str) -> str:
    p = urllib.parse.urlparse(url).path.strip("/").split("/")
    if not p or not p[0]:
        return ""
    h = p[0]
    if h in ("p", "reel", "explore", "popular", "tags", "discover", "pages", "groups", "company", "in", "channel", "watch", "video", "place", "tag", "music", "search", "hashtag", "stories", "reels"):
        return p[1] if len(p) > 1 and h in ("company", "in", "channel") else ""
    return h if h.startswith("@") else "@" + h


def _emails(text: str) -> list[str]:
    out = []
    for e in EMAIL_RE.findall(text or ""):
        e = e.strip(".").lower()
        if not BAD_EMAIL.search(e) and e not in out:
            out.append(e)
    return out[:3]


def _phones(text: str) -> list[str]:
    out = []
    for p in PHONE_RE.findall(text or ""):
        p = re.sub(r"\s+", " ", p.strip())
        if len(re.sub(r"\D", "", p)) >= 10 and p not in out:
            out.append(p)
    return out[:2]


def _scan_site(url: str) -> dict:
    """Homepage + contact page: public email, phone and social links."""
    info = {"emails": [], "phones": [], "socials": []}
    base = f"{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).netloc}"
    pages = [url] if url.rstrip("/") != base else [base]
    pages += [base + "/contact", base + "/contact-us"]
    seen = 0
    for u in pages:
        if seen >= 2 and info["emails"]:
            break
        try:
            st, ct, raw, _ = websearch.http_get(u, timeout=8, max_bytes=800_000)
        except Exception:
            continue
        if st >= 400 or "html" not in ct:
            continue
        seen += 1
        page = websearch._text(raw, ct)
        mailto = re.findall(r"mailto:([^\"'?>\s]+)", page)
        for e in _emails(" ".join(mailto) + " " + re.sub(r"<[^>]+>", " ", page)):
            if e not in info["emails"]:
                info["emails"].append(e)
        for ph in re.findall(r"tel:([+\d][\d\s-]{8,})", page) + _phones(re.sub(r"<[^>]+>", " ", page)):
            ph = ph.strip()
            if ph not in info["phones"] and len(info["phones"]) < 2:
                info["phones"].append(ph)
        for m in re.findall(r'href="(https?://(?:www\.)?(?:instagram|facebook|tiktok|linkedin)\.com/[^"?#]+)', page):
            if m not in info["socials"] and not re.search(r"/(sharer|share|intent|plugins|tr)\b", m):
                info["socials"].append(m)
    info["emails"] = info["emails"][:3]; info["socials"] = info["socials"][:3]
    return info


LISTICLE = re.compile(r"(\b(best|top)\s+\d*|\b\d+\s+best\b|\bguide\b|\blist of\b|\branked\b|\bnear me\b|\bupdated\b|\breviews?\b)", re.I)


def _clean_name(title: str, platform: str) -> str:
    if platform == "Website":
        parts = [p.strip() for p in re.split(r"\s[|–—-]\s|\s·\s|:\s", title or "") if p.strip()]
        parts = [p for p in parts if not re.match(r"^(home|contact( us)?|about( us)?|welcome)$", p, re.I)] or parts
        return (parts[0] if parts else title or "")[:80]
    t = re.sub(r"\s*[•|·–-]\s*(Instagram|TikTok|Facebook|LinkedIn).*$", "", title or "", flags=re.I)
    t = re.sub(r"\s*\(@[^)]+\)", "", t)
    t = re.sub(r"\s+on (Instagram|TikTok).*$", "", t, flags=re.I)
    return t.strip(" -|·")[:80] or title[:80]


def find_leads(niche: str, location: str = "", platform: str = "any", count: int = 20, deadline_s: float = 45) -> dict:
    t0 = time.time()
    niche, location = (niche or "").strip()[:120], (location or "").strip()[:80]
    platform = (platform or "any").lower()
    nl = f"{niche} {location}".strip()
    queries = []
    if platform in ("any", "website", "business", "google"):
        queries += [f"{nl} contact email", f"{nl} official website", f'"{location or niche}" {niche} email phone']
    if platform in ("any", "instagram", "social"):
        queries += [f"site:instagram.com {nl}"]
    if platform in ("any", "tiktok", "social"):
        queries += [f"site:tiktok.com {nl}"]
    if platform in ("facebook", "social"):
        queries += [f"site:facebook.com {nl}"]
    if platform == "linkedin":
        queries += [f"site:linkedin.com/company {nl}", f"site:linkedin.com/in {nl}"]
    results: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(lambda q: websearch.search(q, 15), queries):
            results.extend(res or [])
    rows: dict[str, dict] = {}
    loc_words = [w for w in re.split(r"[\s,]+", location.lower()) if len(w) > 2][:3]
    for r in results:
        url = r["url"].split("#")[0]
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        if any(d in host for d in DIRECTORIES):
            continue
        plat = _platform(url)
        if plat != "Website":
            h = _handle(url)
            if not h or h.lower() in ("@p", "@explore", "@popular"):
                continue
            key = f"{plat}:{h.lower()}"
            link = f"https://{'www.instagram.com' if plat == 'Instagram' else host}/{h.lstrip('@') if plat != 'TikTok' else h}/"
        else:
            key = host.removeprefix("www.")
            link = f"https://{host}/"
        if key in rows:
            continue
        text = f'{r.get("title", "")} {r.get("snippet", "")}'
        if plat == "Website" and LISTICLE.search(r.get("title", "")):
            continue
        if loc_words and not any(w in (text + " " + url).lower() for w in loc_words):
            continue
        rows[key] = {"name": _clean_name(r.get("title", ""), plat), "platform": plat, "handle": _handle(url) if plat != "Website" else "",
                     "link": link, "email": ", ".join(_emails(text)), "phone": ", ".join(_phones(text)),
                     "socials": "", "about": (r.get("snippet") or "")[:200]}
        if len(rows) >= max(count * 2, 30):
            break
    # Enrich websites with public contact details (parallel, time-boxed).
    sites = [k for k, v in rows.items() if v["platform"] == "Website"][:max(count, 12)]
    left = max(5.0, deadline_s - (time.time() - t0))
    ex = cf.ThreadPoolExecutor(max_workers=8)
    if True:
        futs = {ex.submit(_scan_site, rows[k]["link"]): k for k in sites}
        try:
            for f in cf.as_completed(futs, timeout=left):
                k = futs[f]
                try:
                    info = f.result()
                except Exception:
                    continue
                if info["emails"] and not rows[k]["email"]:
                    rows[k]["email"] = ", ".join(info["emails"])
                if info["phones"] and not rows[k]["phone"]:
                    rows[k]["phone"] = ", ".join(info["phones"])
                rows[k]["socials"] = " ".join(info["socials"])
        except cf.TimeoutError:
            pass
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
    ordered = sorted(rows.values(), key=lambda v: (not v["email"], not v["phone"], v["platform"] == "Website"))
    ordered = ordered[:count]
    header = ["#", "Name", "Platform", "Handle", "Link", "Email (public)", "Phone (public)", "Other socials", "About"]
    table = [header] + [[i + 1, r["name"], r["platform"], r["handle"], r["link"], r["email"], r["phone"], r["socials"], r["about"]]
                        for i, r in enumerate(ordered)]
    return {"query": nl, "platform": platform, "count": len(ordered), "rows": table,
            "with_email": sum(1 for r in ordered if r["email"]), "seconds": round(time.time() - t0, 1)}
