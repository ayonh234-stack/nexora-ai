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
                res = blob.get_blob(_url(PREFIX + key + ".json"), access="private")
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

            blob.put_blob(PREFIX + key + ".json", data, access="private", content_type="application/json",
                          allow_overwrite=True, cache_control_max_age=60)
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

        blob.put_blob(PREFIX + key, data, access="private", content_type=content_type, allow_overwrite=True,
                      cache_control_max_age=3600)
    else:
        os.makedirs(_LOCAL, exist_ok=True)
        with open(os.path.join(_LOCAL, key.replace("/", "__")), "wb") as fh:
            fh.write(data)


def get_bytes(key: str) -> bytes | None:
    if _blob_on():
        from vercel.blob import sync as blob

        try:
            res = blob.get_blob(_url(PREFIX + key), access="private")
        except blob.BlobNotFoundError:
            return None
        body = getattr(res, "body", None)
        if body is None and hasattr(res, "read"):
            body = res.read()
        return bytes(body)
    p = os.path.join(_LOCAL, key.replace("/", "__"))
    return open(p, "rb").read() if os.path.exists(p) else None
