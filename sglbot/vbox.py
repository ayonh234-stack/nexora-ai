"""Nexora virtual computer — a small owner-only sandbox on the 24/7 bot box.

Locally (Telegram bot / this machine): run Python, open a real Chrome tab for a
screenshot + readable text, and read/write files in a private workspace.

On Vercel: the same tools call this box through a Cloudflare quick tunnel. The
live URL is published to the shared Blob store (box/endpoint); a shared BOX_TOKEN
authenticates every request. Public users never get these tools.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import resource
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(os.getenv("NEXORA_VBOX_DIR") or "/tmp/nexora-vbox")
WORK = ROOT / "workspace"
TIMEOUT_PY = int(os.getenv("NEXORA_VBOX_PY_TIMEOUT") or 20)
TIMEOUT_BROWSE = int(os.getenv("NEXORA_VBOX_BROWSE_TIMEOUT") or 35)
MEM_MB = int(os.getenv("NEXORA_VBOX_MEM_MB") or 384)
MAX_CODE = 20_000
MAX_STDOUT = 80_000
MAX_FILE = 1_500_000
CHROME = os.getenv("CHROME_BIN") or shutil.which("google-chrome") or shutil.which("chromium") or "/usr/bin/google-chrome"

_PRIVATE = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|169\.254\.|0\.|172\.(1[6-9]|2\d|3[01])\.|::1|\[::1\])|\.internal$|\.local$|\.localhost$",
    re.I,
)
_SENSITIVE_NAME = re.compile(r"(^\.env($|\.)|vaul[tk]|credentials|id_rsa|id_ed25519|\.pem$|secret|\.git/config)", re.I)
_lock = threading.Lock()
_rate: list[float] = []
RATE_PER_HOUR = 40


def _ensure() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp").mkdir(parents=True, exist_ok=True)


def is_local() -> bool:
    """True when this process can run the computer itself (the box, not Vercel)."""
    if os.getenv("VERCEL"):
        return False
    if (os.getenv("NEXORA_VBOX_LOCAL") or "").strip() == "1":
        return True
    return Path(CHROME).exists() and not os.getenv("VERCEL")


def _token() -> str:
    return (os.getenv("BOX_TOKEN") or "").strip()


def _remote_url() -> str:
    env = (os.getenv("BOX_URL") or "").strip().rstrip("/")
    if env:
        return env
    try:
        from sglbot import store
        rec = store.get("box/endpoint", None, max_age=20) or {}
        url = (rec.get("url") or "").strip().rstrip("/")
        if url.startswith("https://"):
            return url
    except Exception as exc:
        logger.warning("vbox endpoint read failed: %s", str(exc)[:160])
    return ""


def publish_endpoint(url: str) -> None:
    """Called by the tunnel supervisor when the public URL changes."""
    from sglbot import store
    store.put("box/endpoint", {"url": url.rstrip("/"), "updated": time.time()})


def available() -> dict:
    if is_local():
        return {"online": True, "where": "local"}
    url = _remote_url()
    if not url or not _token():
        return {"online": False, "where": "remote", "reason": "not configured"}
    try:
        req = urllib.request.Request(
            url + "/v1/health",
            headers={"Authorization": "Bearer " + _token(), "User-Agent": "NexoraAI-VBox/1"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            body = json.loads(r.read(4000).decode("utf-8", "ignore") or "{}")
        return {"online": bool(body.get("ok")), "where": "remote", "url_host": urllib.parse.urlparse(url).netloc}
    except Exception as exc:
        return {"online": False, "where": "remote", "reason": str(exc)[:160]}


def warming_message(bn: bool = True) -> str:
    if bn:
        return "কম্পিউটার চালু হচ্ছে…"
    return "Starting the computer…"


def offline_message(bn: bool = True) -> str:
    if bn:
        return ("ভার্চুয়াল কম্পিউটার এখন অফলাইন, অথবা জাগতে একটু বেশি সময় নিচ্ছে। "
                "এক মিনিট পরে আবার চেষ্টা করুন। টেলিগ্রাম বটেও (@SocialGrowthLabAI_bot) এটা কাজ করে।")
    return ("The virtual computer is offline, or it is taking too long to wake up. "
            "Try again in a minute. It also works in the Telegram bot (@SocialGrowthLabAI_bot).")


def _check_rate() -> str | None:
    now = time.time()
    _rate[:] = [t for t in _rate if now - t < 3600]
    if len(_rate) >= RATE_PER_HOUR:
        return "hourly limit reached"
    _rate.append(now)
    return None


# ---------------------------------------------------------------- path safety

def _safe_path(name: str) -> Path:
    _ensure()
    raw = (name or "").strip().lstrip("/")
    if not raw or raw in (".", "..") or ".." in Path(raw).parts:
        raise ValueError("invalid file name")
    path = (WORK / raw).resolve()
    work = WORK.resolve()
    if path != work and work not in path.parents:
        raise ValueError("path outside workspace")
    if _SENSITIVE_NAME.search(path.name):
        raise ValueError("that file name is not allowed")
    return path


def _public_http(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("www."):
        u = "https://" + u
    if not re.match(r"^https?://", u, re.I):
        raise ValueError("only public http(s) URLs are allowed")
    parts = urllib.parse.urlparse(u)
    host = (parts.hostname or "").strip().strip("[]").lower()
    if not host or _PRIVATE.search(host) or host == "0.0.0.0":
        raise ValueError("private or local addresses are blocked")
    try:
        # 198.18.0.0/15 is "benchmarking" and Python marks it private, but this box's
        # egress proxy uses that range, so real public sites resolve there. Still block RFC1918.
        egress = ipaddress.ip_network("198.18.0.0/15")
        for fam, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip in egress:
                continue
            if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                raise ValueError("private or local addresses are blocked")
            if ip.is_private:
                raise ValueError("private or local addresses are blocked")
    except socket.gaierror as exc:
        raise ValueError(f"could not resolve host: {exc}") from exc
    return u


# ---------------------------------------------------------------- python

_RUNNER = r'''
import builtins, os, sys, resource
work = os.environ.get("NEXORA_WORK", ".")
os.chdir(work)
try:
    resource.setrlimit(resource.RLIMIT_CPU, ({cpu}, {cpu}))
    resource.setrlimit(resource.RLIMIT_AS, ({mem}, {mem}))
    resource.setrlimit(resource.RLIMIT_FSIZE, ({fsize}, {fsize}))
    resource.setrlimit(resource.RLIMIT_NPROC, (48, 48))
except Exception:
    pass
blocked = {blocked!r}
real_open = builtins.open

def _blocked(path):
    p = os.path.abspath(str(path))
    name = os.path.basename(p)
    if name.startswith(".env") or name in ("VAULT_KEY", "id_rsa", "id_ed25519"):
        return True
    for b in blocked:
        if p == b or p.startswith(b.rstrip("/") + "/"):
            return True
    # never read the bot or app secrets / this runner
    if "/sgl-telegram-bot/.env" in p or "/nexora-app/.env" in p or p.endswith("/.render_key"):
        return True
    return False

def _open(file, *a, **k):
    if _blocked(file):
        raise PermissionError("access denied")
    return real_open(file, *a, **k)
builtins.open = _open
src = open({src!r}, encoding="utf-8").read()
# re-bind open after reading the source, already done
ns = {{"__name__": "__main__", "__file__": {src!r}}}
exec(compile(src, "user.py", "exec"), ns, ns)
'''


def _blocked_dirs() -> list[str]:
    paths = [
        "/workspace/sgl-telegram-bot/.env",
        "/workspace/nexora-app/.env",
        str(Path.home() / ".ssh"),
        "/etc/shadow",
        "/etc/ssl/private",
        "/root",
        "/cursor",
        "/home/box/.cursor",
    ]
    for key in ("TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "VAULT_KEY", "BLOB_READ_WRITE_TOKEN", "BOX_TOKEN", "XAI_API_KEY"):
        # nothing to add; just ensure env is stripped
        _ = key
    return paths


def run_python(code: str) -> dict:
    code = (code or "").strip()
    if not code:
        return {"error": "empty code"}
    if len(code) > MAX_CODE:
        return {"error": f"code too long (max {MAX_CODE} characters)"}
    err = _check_rate()
    if err:
        return {"error": err}
    _ensure()
    before = {p.resolve(): p.stat().st_mtime for p in WORK.rglob("*") if p.is_file()}
    with tempfile.TemporaryDirectory(dir=str(ROOT / "tmp")) as td:
        src = Path(td) / "user.py"
        runner = Path(td) / "runner.py"
        src.write_text(code, encoding="utf-8")
        runner.write_text(
            _RUNNER.format(
                cpu=TIMEOUT_PY,
                mem=MEM_MB * 1024 * 1024,
                fsize=8 * 1024 * 1024,
                blocked=_blocked_dirs(),
                src=str(src),
            ),
            encoding="utf-8",
        )
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(WORK),
            "TMPDIR": td,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "NEXORA_WORK": str(WORK),
        }
        py = shutil.which("python3") or sys_executable()
        try:
            proc = subprocess.run(
                [py, "-I", str(runner)],
                cwd=str(WORK),
                env=env,
                capture_output=True,
                timeout=TIMEOUT_PY + 3,
                text=True,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return {"error": f"timed out after {TIMEOUT_PY}s", "stdout": "", "stderr": ""}
    stdout = (proc.stdout or "")[:MAX_STDOUT]
    stderr = _clean_stderr(proc.stderr or "")[:20_000]
    new_files = _new_files(before)
    return {
        "ok": proc.returncode == 0,
        "exit": proc.returncode,
        "stdout": stdout or "(no output)",
        "stderr": stderr,
        "files_created": [f["name"] for f in new_files],
        "_files": new_files,
    }


def sys_executable() -> str:
    return os.environ.get("PYTHON", "/usr/bin/python3")


def _clean_stderr(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if "Failed to connect to the bus" in line or "libudev" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _new_files(before: dict) -> list[dict]:
    out = []
    work = WORK.resolve()
    for p in WORK.rglob("*"):
        if not p.is_file():
            continue
        path = p.resolve()
        if path.suffix in {".pyc"} or path.name.startswith("."):
            continue
        if path in before and p.stat().st_mtime <= before[path] + 0.01:
            continue
        size = p.stat().st_size
        if size <= 0 or size > MAX_FILE:
            continue
        rel = str(path.relative_to(work))
        if _SENSITIVE_NAME.search(rel):
            continue
        out.append({"name": rel, "mime": _mime(path), "data": path.read_bytes()[:MAX_FILE], "size": size})
    return out[:8]


def _mime(path: Path) -> str:
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
        ".webp": "image/webp", ".pdf": "application/pdf", ".csv": "text/csv",
        ".txt": "text/plain", ".md": "text/markdown", ".json": "application/json",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".mp3": "audio/mpeg", ".mp4": "video/mp4", ".zip": "application/zip",
        ".py": "text/x-python", ".html": "text/html",
    }.get(path.suffix.lower(), "application/octet-stream")


# ---------------------------------------------------------------- browse (system Chrome, no paid browser service)

def _jpeg(png: bytes, quality: int = 75, width: int = 960) -> bytes:
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(png)).convert("RGB")
        if im.width > width:
            h = int(im.height * (width / im.width))
            im = im.resize((width, h))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception:
        return png


def _html_text(html: str, limit: int = 8000) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        title = (soup.title.get_text(" ", strip=True) if soup.title else "") or ""
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True)).strip()
        if title and title not in text[:200]:
            text = title + "\n\n" + text
        return text[:limit]
    except Exception:
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:limit]


def _browse_text_only(url: str, note: str, html: str = "", detail: str = "") -> dict:
    """Fallback when Chromium cannot take a screenshot (common on 512 MB hosts)."""
    if not html:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 NexoraComputer/1", "Accept": "text/html,application/xhtml+xml"},
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read(1_500_000)
                enc = r.headers.get_content_charset() or "utf-8"
            html = raw.decode(enc, "replace")
        except Exception as exc:
            return {"error": note, "detail": (detail or str(exc))[:400], "url": url, "screenshot": False}
    text = _html_text(html)
    out = {
        "ok": True,
        "url": url,
        "title": (text.split("\n", 1)[0] if text else "")[:160],
        "text": text or "(no readable text)",
        "screenshot": False,
        "note": note,
    }
    if detail:
        out["detail"] = detail
    return out


def browse(url: str, wait_ms: int = 4000) -> dict:
    err = _check_rate()
    if err:
        return {"error": err}
    try:
        url = _public_http(url)
    except ValueError as exc:
        return {"error": str(exc)}
    if not Path(CHROME).exists():
        return _browse_text_only(url, "browser is not installed; text only")
    wait_ms = max(0, min(int(wait_ms or 4000), 15000))
    _ensure()
    with _lock:
        with tempfile.TemporaryDirectory(dir=str(ROOT / "tmp"), prefix="chrome-") as td:
            shot = Path(td) / "shot.png"
            # Do not set --user-data-dir: in this environment Chrome hangs with a custom profile.
            cmd = [
                CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                "--disable-dev-shm-usage", "--hide-scrollbars", "--disable-extensions",
                "--no-first-run",
                "--window-size=1280,800",
                f"--screenshot={shot}",
                f"--virtual-time-budget={max(wait_ms, 2000)}",
                "--dump-dom",
                url,
            ]
            if (os.getenv("NEXORA_VBOX_LOWMEM") or "").strip() == "1":
                cmd[1:1] = ["--single-process", "--no-zygote", "--js-flags=--max-old-space-size=128"]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, timeout=TIMEOUT_BROWSE, text=True, errors="replace",
                )
            except subprocess.TimeoutExpired:
                return _browse_text_only(url, "page load timed out; text only")
            html = proc.stdout or ""
            if not shot.exists() or shot.stat().st_size < 100:
                errl = _clean_stderr(proc.stderr or "")[:400]
                return _browse_text_only(url, "screenshot unavailable; text only", html=html, detail=errl)
            png = shot.read_bytes()
    jpeg = _jpeg(png)
    name = "screenshot.jpg" if jpeg[:3] == b"\xff\xd8\xff" else "screenshot.png"
    mime = "image/jpeg" if name.endswith(".jpg") else "image/png"
    text = _html_text(html)
    return {
        "ok": True,
        "url": url,
        "title": (text.split("\n", 1)[0] if text else "")[:160],
        "text": text or "(no readable text)",
        "bytes": len(jpeg),
        "screenshot": True,
        "_files": [{"name": name, "mime": mime, "data": jpeg, "size": len(jpeg)}],
    }


# ---------------------------------------------------------------- files

def computer_file(action: str, name: str = "", content: str = "") -> dict:
    _ensure()
    action = (action or "list").lower().strip()
    if action == "list":
        items = []
        work = WORK.resolve()
        for p in sorted(WORK.rglob("*")):
            if p.is_file() and not p.name.startswith(".") and p.suffix != ".pyc":
                rel = str(p.resolve().relative_to(work))
                items.append({"name": rel, "bytes": p.stat().st_size})
        return {"ok": True, "files": items[:80], "cwd": "workspace"}
    if action == "write":
        err = _check_rate()
        if err:
            return {"error": err}
        try:
            path = _safe_path(name)
        except ValueError as exc:
            return {"error": str(exc)}
        data = (content or "").encode("utf-8")
        if len(data) > MAX_FILE:
            return {"error": "file too large"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"ok": True, "written": str(path.relative_to(WORK.resolve())), "bytes": len(data)}
    if action in ("read", "download"):
        try:
            path = _safe_path(name)
        except ValueError as exc:
            return {"error": str(exc)}
        if not path.is_file():
            return {"error": "file not found"}
        data = path.read_bytes()[:MAX_FILE]
        if action == "download" or _mime(path).startswith("image/") or len(data) > 40_000:
            return {
                "ok": True,
                "name": str(path.relative_to(WORK.resolve())),
                "bytes": len(data),
                "_files": [{"name": path.name, "mime": _mime(path), "data": data, "size": len(data)}],
            }
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        return {"ok": True, "name": str(path.relative_to(WORK.resolve())), "text": text[:20000], "bytes": len(data)}
    return {"error": "action must be list, read, write or download"}


# ---------------------------------------------------------------- dispatch (local or remote)

def run(op: str, args: dict) -> dict:
    """Public entry used by agent tools. Runs locally on the box, otherwise calls the tunnel."""
    op = (op or "").strip()
    if is_local():
        return _dispatch(op, args or {})
    return _remote(op, args or {})


def _dispatch(op: str, args: dict) -> dict:
    if op == "python":
        return run_python(args.get("code") or "")
    if op == "browse":
        return browse(args.get("url") or "", args.get("wait_ms") or 4000)
    if op == "file":
        return computer_file(args.get("action") or "list", args.get("name") or "", args.get("content") or "")
    if op == "status":
        return {"ok": True, **available(), "workspace": str(WORK)}
    return {"error": f"unknown op {op}"}


def _remote(op: str, args: dict) -> dict:
    url = _remote_url()
    token = _token()
    if not url or not token:
        return {"error": "offline", "detail": "virtual computer endpoint is not configured"}
    body = json.dumps({"op": op, "args": args}, ensure_ascii=False).encode()
    deadline = time.time() + int(os.getenv("NEXORA_VBOX_WARM_SEC") or 60)
    last_err = "offline"
    attempt = 0
    while True:
        attempt += 1
        try:
            req = urllib.request.Request(
                url + "/v1/run",
                data=body,
                method="POST",
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                    "User-Agent": "NexoraAI-VBox/1",
                },
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_BROWSE + 25) as r:
                raw = r.read(8_000_000)
            text = raw.decode("utf-8", "replace")
            if text.lstrip()[:1] != "{":
                last_err = "warming"
                raise RuntimeError("non-json response (host is waking)")
            payload = json.loads(text)
            break
        except urllib.error.HTTPError as exc:
            detail = (exc.read(2000) or b"").decode("utf-8", "ignore")
            if exc.code in (502, 503, 504, 408, 429) and time.time() < deadline:
                last_err = f"HTTP {exc.code}"
                time.sleep(min(6, 2 + attempt))
                continue
            return {"error": f"computer HTTP {exc.code}", "detail": detail[:400]}
        except Exception as exc:
            last_err = str(exc)[:200]
            if time.time() < deadline:
                time.sleep(min(6, 2 + attempt))
                continue
            return {"error": "offline", "detail": last_err, "warming": True}

    # files arrive as base64
    files = []
    for f in payload.get("files") or payload.get("_files") or []:
        if not isinstance(f, dict) or not f.get("data"):
            continue
        try:
            import base64
            data = base64.b64decode(f["data"])
        except Exception:
            continue
        files.append({"name": f.get("name") or "file", "mime": f.get("mime") or "application/octet-stream",
                      "data": data, "size": len(data)})
    payload["_files"] = files
    payload.pop("files", None)
    return payload


def pack_files(result: dict) -> list[dict]:
    files = result.pop("_files", None) or []
    # also drop any leftover raw bytes before the model sees the tool output
    return files
