"""Free web search + page reading (no API keys): Bing/DuckDuckGo/Startpage HTML, Wikipedia, YouTube transcripts."""

from __future__ import annotations

import base64
import concurrent.futures as cf
import gzip
import html as htmllib
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
_HDR = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Encoding": "gzip, deflate"}
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/17.5 Mobile/15E148 Safari/604.1")
MAX_BYTES = 3_000_000


def http_get(url: str, timeout: float = 15, headers: dict | None = None, data: bytes | None = None,
             max_bytes: int = MAX_BYTES) -> tuple[int, str, bytes, str]:
    """(status, content-type, body, final url). Never raises for HTTP errors."""
    h = dict(_HDR); h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        status, ctype, final = r.status, r.headers.get("content-type", ""), r.geturl()
        raw = r.read(max_bytes + 1)
        enc = (r.headers.get("content-encoding") or "").lower()
    except urllib.error.HTTPError as e:
        status, ctype, final = e.code, e.headers.get("content-type", "") if e.headers else "", url
        try:
            raw = e.read(200_000)
        except Exception:
            raw = b""
        enc = (e.headers.get("content-encoding") or "").lower() if e.headers else ""
    try:
        if enc == "gzip":
            raw = gzip.decompress(raw)
        elif enc == "deflate":
            raw = zlib.decompress(raw)
    except Exception:
        pass
    return status, ctype, raw[:max_bytes], final


def _text(raw: bytes, ctype: str = "") -> str:
    m = re.search(r"charset=([\w-]+)", ctype or "")
    for enc in ([m.group(1)] if m else []) + ["utf-8", "latin-1"]:
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


# ---------------------------------------------------------------- search engines
def _bing(query: str, n: int) -> list[dict]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "count": min(30, n + 5), "setlang": "en"})
    st, ct, raw, _ = http_get(url, timeout=12, headers={"User-Agent": MOBILE_UA})
    if st != 200:
        raise RuntimeError(f"bing {st}")
    page = _text(raw, ct)
    out = []
    for block in re.findall(r'<li class="b_algo"(.*?)</li>', page, re.S):
        a = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not a:
            continue
        href = htmllib.unescape(a.group(1))
        if "bing.com/ck/a" in href:
            u = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("u", [""])[0]
            if u.startswith("a1"):
                try:
                    href = base64.urlsafe_b64decode(u[2:] + "=" * (-len(u[2:]) % 4)).decode()
                except Exception:
                    continue
        p = re.search(r'<p[^>]*>(.*?)</p>', block, re.S) or re.search(r'class="b_lineclamp\d"[^>]*>(.*?)</', block, re.S)
        if href.startswith("http"):
            out.append({"title": _clean(a.group(2)), "url": href, "snippet": _clean(p.group(1)) if p else ""})
    return out


def _ddg(query: str, n: int) -> list[dict]:
    st, ct, raw, _ = http_get("https://html.duckduckgo.com/html/", timeout=12,
                              data=urllib.parse.urlencode({"q": query}).encode())
    page = _text(raw, ct)
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)', page, re.S):
        href = htmllib.unescape(m.group(1))
        if "uddg=" in href:
            href = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [""])[0])
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', m.group(3), re.S)
        if href.startswith("http"):
            out.append({"title": _clean(m.group(2)), "url": href, "snippet": _clean(sn.group(1)) if sn else ""})
    if not out:
        raise RuntimeError("ddg blocked/empty")
    return out


def _md_results(md: str) -> list[dict]:
    """Parse r.jina.ai markdown of a DDG/Bing results page."""
    out = []
    blocks = re.split(r"\n(?=\s*(?:\d+\.\s+)?##\s*\[)", md)
    for b in blocks:
        m = re.match(r"\s*(?:\d+\.\s+)?##\s*\[(.+?)\]\((https?://[^)\s]+)\)", b, re.S)
        if not m:
            continue
        href = m.group(2)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        if "uddg" in q:
            href = q["uddg"][0]
        elif "bing.com/ck/a" in href and q.get("u", [""])[0].startswith("a1"):
            u = q["u"][0][2:]
            try:
                href = base64.urlsafe_b64decode(u + "=" * (-len(u) % 4)).decode()
            except Exception:
                continue
        if "duckduckgo.com" in href or "bing.com" in href:
            continue
        rest = b[m.end():]
        snippet = ""
        for line in rest.split("\n"):
            line = line.strip()
            line = re.sub(r"\[?!\[[^\]]*\]\([^)]*\)\]?(\([^)]*\))?", "", line).strip()
            whole = re.match(r"^\[(.*)\]\([^)]*\)$", line, re.S)
            if whole:
                line = whole.group(1)
            line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line).replace("**", "").strip()
            if not line or re.match(r"^(www\.|https?://)?[\w.-]+\.[a-z]{2,}(/\S*)?$", line) or len(line) < 25:
                continue
            snippet = line
            break
        title = re.sub(r"\*\*", "", m.group(1))
        out.append({"title": _clean(title), "url": href, "snippet": _clean(snippet)[:300]})
    return out


def _jina(target: str) -> str:
    st, ct, raw, _ = http_get("https://r.jina.ai/" + target, timeout=25, headers={"Accept": "text/plain", "X-No-Cache": "true"})
    if st != 200:
        raise RuntimeError(f"jina {st}")
    return _text(raw, ct)


def _jina_ddg(query: str, n: int) -> list[dict]:
    res = _md_results(_jina("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)))
    if not res:
        raise RuntimeError("jina-ddg empty")
    return res


def _jina_bing(query: str, n: int) -> list[dict]:
    res = _md_results(_jina("https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&count=20"))
    if not res:
        raise RuntimeError("jina-bing empty")
    return res


def _startpage(query: str, n: int) -> list[dict]:
    st, ct, raw, _ = http_get("https://www.startpage.com/do/search?" + urllib.parse.urlencode({"q": query}), timeout=12)
    page = _text(raw, ct)
    out = []
    for m in re.finditer(r'<a[^>]+class="[^"]*result-title[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=class="[^"]*result-title|$)', page, re.S):
        sn = re.search(r'<p[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</p>', m.group(3), re.S)
        if m.group(1).startswith("http"):
            out.append({"title": _clean(m.group(2)), "url": htmllib.unescape(m.group(1)), "snippet": _clean(sn.group(1)) if sn else ""})
    if not out:
        raise RuntimeError("startpage empty")
    return out


def news(query: str, n: int = 8, lang: str = "en") -> list[dict]:
    """Latest news via Google News RSS (free, no key)."""
    hl, gl = ("bn", "BD") if lang == "bn" else ("en-US", "US")
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": hl, "gl": gl, "ceid": f"{gl}:{hl.split('-')[0]}"})
    st, ct, raw, _ = http_get(url, timeout=12)
    out = []
    for it in re.findall(r"<item>(.*?)</item>", _text(raw, ct), re.S)[:n]:
        g = lambda tag: _clean((re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", it, re.S) or [None, ""])[1].replace("<![CDATA[", "").replace("]]>", ""))
        out.append({"title": g("title"), "url": g("link"), "snippet": f'{g("source")} · {g("pubDate")}'})
    return out


def wikipedia(query: str, n: int = 3, lang: str = "en") -> list[dict]:
    api = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": n, "utf8": 1})
    st, ct, raw, _ = http_get(api, timeout=10, headers={"User-Agent": "NexoraAI/1.0 (contact: socialgrowthlab)"})
    out = []
    for r in (json.loads(raw or b"{}").get("query") or {}).get("search", [])[:n]:
        title = r.get("title", "")
        out.append({"title": title + " — Wikipedia", "url": f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                    "snippet": _clean(r.get("snippet", ""))})
    return out


def search(query: str, n: int = 8) -> list[dict]:
    """Best-effort free web search. Tries several engines until one answers."""
    query = (query or "").strip()[:300]
    if not query:
        return []
    for engine in (_ddg, _jina_ddg, _jina_bing, _bing):
        try:
            res = engine(query, n)
            seen, out = set(), []
            for r in res:
                key = r["url"].split("#")[0].rstrip("/")
                if key in seen:
                    continue
                seen.add(key); out.append(r)
            if out:
                return out[:n]
        except Exception as exc:
            logger.warning("search engine %s failed: %s", engine.__name__, str(exc)[:120])
    try:
        return wikipedia(query, min(n, 5))
    except Exception:
        return []


# ---------------------------------------------------------------- reading pages
_YT = re.compile(r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/|live/)|youtu\.be/)([\w-]{11})")


def youtube(url: str) -> dict:
    vid = _YT.search(url).group(1)
    title = ""
    try:
        st, ct, raw, _ = http_get("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url), timeout=10)
        if st == 200:
            o = json.loads(raw); title = f'{o.get("title", "")} — {o.get("author_name", "")}'
    except Exception:
        pass
    text = ""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()
        tl = api.list(vid)
        langs = [t.language_code for t in tl]
        pick = next((l for l in ("bn", "en", "en-US", "hi") if l in langs), langs[0] if langs else None)
        if pick:
            fetched = api.fetch(vid, languages=[pick])
            text = " ".join(s.text for s in fetched)
    except Exception as exc:
        logger.warning("youtube transcript failed: %s", str(exc)[:160])
    if not text:
        # Fall back to the public description on the watch page.
        st, ct, raw, _ = http_get(f"https://www.youtube.com/watch?v={vid}", timeout=12)
        m = re.search(r'"shortDescription":"(.*?)","', _text(raw, ct))
        if m:
            text = "[No transcript available — video description only]\n" + json.loads('"' + m.group(1) + '"')
    return {"url": url, "title": title or f"YouTube video {vid}", "text": text[:60000]}


def _readable(page: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    for t in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside", "iframe", "button"]):
        t.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    parts = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "blockquote", "pre"]):
        tx = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if len(tx) < 25 and el.name not in ("h1", "h2", "h3", "h4"):
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            tx = "## " + tx
        elif el.name == "li":
            tx = "- " + tx
        if not parts or parts[-1] != tx:
            parts.append(tx)
    text = "\n".join(parts)
    if len(text) < 200:
        text = re.sub(r"\s+", " ", root.get_text(" ", strip=True))
    if desc and desc.get("content") and len(text) < 400:
        text = desc["content"].strip() + "\n" + text
    return title, text


def read_url(url: str, max_chars: int = 40000) -> dict:
    """Fetch a page (or PDF/YouTube) and return its readable text."""
    url = (url or "").strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host or host in ("localhost",) or re.match(r"^(127\.|10\.|192\.168\.|169\.254\.|0\.)", host) or host.endswith(".internal"):
        return {"url": url, "error": "blocked address"}
    if _YT.search(url):
        return youtube(url)
    st, ct, raw, final = http_get(url, timeout=20)
    if st >= 400:
        return {"url": url, "error": f"HTTP {st}"}
    if "pdf" in ct or final.lower().endswith(".pdf"):
        from sglbot import files

        return {"url": final, "title": final.rsplit("/", 1)[-1], "text": files.extract_text(raw, "x.pdf")[:max_chars]}
    if "json" in ct or "text/plain" in ct:
        return {"url": final, "title": final, "text": _text(raw, ct)[:max_chars]}
    title, text = _readable(_text(raw, ct))
    if len(text) < 500:  # JS-rendered page: let the free reader proxy render it
        try:
            md = _jina(final)
            if len(md) > len(text) + 200:
                md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)
                text = re.sub(r"\n{3,}", "\n\n", md)
        except Exception:
            pass
    return {"url": final, "title": title, "text": text[:max_chars]}


def read_many(urls: list[str], max_chars: int = 8000, workers: int = 6, timeout: float = 25) -> list[dict]:
    out: list[dict] = []
    ex = cf.ThreadPoolExecutor(max_workers=workers)
    futs = {ex.submit(read_url, u, max_chars): u for u in urls}
    try:
        for f in cf.as_completed(futs, timeout=timeout):
            try:
                r = f.result()
            except Exception as exc:
                r = {"url": futs[f], "error": str(exc)[:100]}
            r["src"] = futs[f]
            out.append(r)
    except cf.TimeoutError:
        pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out
