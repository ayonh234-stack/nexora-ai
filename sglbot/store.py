"""Tiny JSON key-value store on the free private Vercel Blob store (shared by the web app and the bot).
Falls back to a local folder when BLOB_READ_WRITE_TOKEN is not set."""

from __future__ import annotations

import json
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)
_LOCAL = os.getenv("NEXORA_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "kv")
_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}
PREFIX = "nexora/"


BLOB_TIMEOUT = float(os.getenv("BLOB_TIMEOUT") or 25)


def _bounded(fn, *a, **kw):
    """Run a blob SDK call with a hard deadline (its downloads have no read timeout, so a dead connection could hang)."""
    box: dict = {}

    def run():
        try:
            box["v"] = fn(*a, **kw)
        except BaseException as exc:  # re-raised in the caller's thread
            box["e"] = exc

    t = threading.Thread(target=run, daemon=True, name="blob-call")
    t.start()
    t.join(BLOB_TIMEOUT)
    if t.is_alive():
        raise TimeoutError(f"blob call timed out after {BLOB_TIMEOUT:.0f}s")
    if "e" in box:
        raise box["e"]
    return box.get("v")


def _blob_on() -> bool:
    return bool(os.getenv("BLOB_READ_WRITE_TOKEN"))


def _url(path: str) -> str:
    """Full private URL + cache-buster: overwritten blobs can otherwise be served stale for up to a minute."""
    tok = os.getenv("BLOB_READ_WRITE_TOKEN", "")
    parts = tok.split("_")
    if len(parts) >= 5 and parts[3]:
        return f"https://{parts[3].lower()}.private.blob.vercel-storage.com/{path}?t={time.time():.6f}"
    return path


def get(key: str, default=None, max_age: float = 0):
    now = time.time()
    if max_age and key in _cache and now - _cache[key][0] < max_age:
        return _cache[key][1]
    val = default
    try:
        if _blob_on():
            from vercel.blob import sync as blob

            try:
                res = _bounded(blob.get_blob, _url(PREFIX + key + ".json"), access="private")
                body = getattr(res, "body", None)
                if body is None and hasattr(res, "read"):
                    body = res.read()
                val = json.loads(bytes(body).decode("utf-8"))
            except blob.BlobNotFoundError:
                val = default
        else:
            p = os.path.join(_LOCAL, key.replace("/", "__") + ".json")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    val = json.load(fh)
    except Exception as exc:
        logger.warning("store.get %s failed: %s", key, str(exc)[:160])
        raise
    _cache[key] = (now, val)
    return val


def put(key: str, value) -> None:
    data = json.dumps(value, ensure_ascii=False).encode("utf-8")
    with _lock:
        if _blob_on():
            from vercel.blob import sync as blob

            _bounded(blob.put_blob, PREFIX + key + ".json", data, access="private", content_type="application/json",
                          allow_overwrite=True, cache_control_max_age=0)
        else:
            os.makedirs(_LOCAL, exist_ok=True)
            p = os.path.join(_LOCAL, key.replace("/", "__") + ".json")
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(data.decode("utf-8"))
            os.replace(tmp, p)
            os.chmod(p, 0o600)
    _cache[key] = (time.time(), value)


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    """Binary object (e.g. an image waiting to be published to Instagram)."""
    if _blob_on():
        from vercel.blob import sync as blob

        _bounded(blob.put_blob, PREFIX + key, data, access="private", content_type=content_type, allow_overwrite=True,
                      cache_control_max_age=3600)
    else:
        os.makedirs(_LOCAL, exist_ok=True)
        with open(os.path.join(_LOCAL, key.replace("/", "__")), "wb") as fh:
            fh.write(data)


def get_bytes(key: str) -> bytes | None:
    if _blob_on():
        from vercel.blob import sync as blob

        try:
            res = _bounded(blob.get_blob, _url(PREFIX + key), access="private")
        except blob.BlobNotFoundError:
            return None
        body = getattr(res, "body", None)
        if body is None and hasattr(res, "read"):
            body = res.read()
        return bytes(body)
    p = os.path.join(_LOCAL, key.replace("/", "__"))
    return open(p, "rb").read() if os.path.exists(p) else None


def list_keys(prefix: str) -> list[str]:
    """Relative keys (no .json suffix) under PREFIX+prefix, newest names last."""
    if _blob_on():
        from vercel.blob import sync as blob

        def _all():
            return list(blob.query_blobs(prefix=PREFIX + prefix, page_size=100))

        items = _bounded(_all)
        keys = []
        for item in items:
            path = getattr(item, "pathname", "") or ""
            if path.startswith(PREFIX):
                rel = path[len(PREFIX):]
                if rel.endswith(".json"):
                    rel = rel[:-5]
                keys.append(rel)
        keys.sort()
        return keys
    os.makedirs(_LOCAL, exist_ok=True)
    out = []
    pref = prefix.replace("/", "__")
    for name in sorted(os.listdir(_LOCAL)):
        if not name.endswith(".json"):
            continue
        rel = name[:-5].replace("__", "/")
        if rel.startswith(prefix):
            out.append(rel)
    return out


def delete(key: str) -> None:
    if _blob_on():
        from vercel.blob import sync as blob
        try:
            _bounded(blob.delete_blob, PREFIX + key + ".json")
        except Exception as exc:
            logger.warning("store.delete %s failed: %s", key, str(exc)[:160])
    else:
        p = os.path.join(_LOCAL, key.replace("/", "__") + ".json")
        if os.path.exists(p):
            os.remove(p)
    _cache.pop(key, None)
