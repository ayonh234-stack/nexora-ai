"""Owner-only encrypted vault (AES-256-GCM, key in VAULT_KEY env). Shared by the web app and the Telegram bot
through the private Blob store. Secrets are only ever decrypted inside tools; they are never shown in chat."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time

from sglbot import store

NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,48}$")


class VaultError(RuntimeError):
    pass


def _key() -> bytes:
    raw = (os.getenv("VAULT_KEY") or "").strip()
    if not raw:
        raise VaultError("vault is not configured (VAULT_KEY missing)")
    k = base64.b64decode(raw)
    if len(k) != 32:
        raise VaultError("VAULT_KEY must be 32 bytes (base64)")
    return k


def enabled() -> bool:
    try:
        _key(); return True
    except Exception:
        return False


def _enc(obj) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    ct = AESGCM(_key()).encrypt(nonce, json.dumps(obj, ensure_ascii=False).encode(), b"nexora-vault-v1")
    return {"v": 1, "n": base64.b64encode(nonce).decode(), "c": base64.b64encode(ct).decode(), "t": time.time()}


def _dec(box: dict):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not box:
        return {}
    pt = AESGCM(_key()).decrypt(base64.b64decode(box["n"]), base64.b64decode(box["c"]), b"nexora-vault-v1")
    return json.loads(pt)


def _load(max_age: float = 0) -> dict:
    return _dec(store.get("vault/entries", None, max_age=max_age))


def _save(entries: dict) -> None:
    store.put("vault/entries", _enc(entries))


def list_entries() -> list[dict]:
    """Names, notes and kinds only — never values."""
    return [{"name": k, "note": v.get("note", ""), "kind": v.get("kind", "secret"),
             "updated": time.strftime("%Y-%m-%d", time.gmtime(v.get("updated", 0)))} for k, v in sorted(_load().items())]


def set_entry(name: str, value: str, note: str = "", kind: str = "secret") -> None:
    name = (name or "").strip()
    if not NAME_RE.match(name):
        raise VaultError("name must be 1-48 letters, digits, _ . -")
    if not value:
        raise VaultError("empty value")
    e = _load()
    e[name] = {"value": value[:8000], "note": (note or "")[:300], "kind": kind or "secret", "updated": time.time()}
    _save(e)


def delete_entry(name: str) -> bool:
    e = _load()
    if name in e:
        del e[name]; _save(e); return True
    return False


def get_value(name: str, max_age: float = 0) -> str:
    e = _load(max_age)
    if name not in e:
        raise VaultError(f"no vault entry named {name}")
    return e[name]["value"]


def has_entry(name: str, max_age: float = 0) -> bool:
    try:
        return name in _load(max_age)
    except Exception:
        return False


def secret_values() -> list[str]:
    try:
        return [v["value"] for v in _load(30).values() if len(v.get("value", "")) >= 4]
    except Exception:
        return []


def redact(text: str, values: list[str] | None = None) -> str:
    for v in sorted(values if values is not None else secret_values(), key=len, reverse=True):
        if v and len(v) >= 4:
            text = text.replace(v, "[vault-secret]")
    return text


# ---------------------------------------------------------------- PIN + owner sessions (web)
def _hmac(msg: str) -> str:
    return hmac.new(_key(), msg.encode(), hashlib.sha256).hexdigest()


def has_pin() -> bool:
    return bool(store.get("vault/pin", None))


def setup_code(window: int | None = None) -> str:
    """6-digit one-time code (valid ~10-20 min) sent to the owner's Telegram to authorise PIN setup/reset."""
    w = int(time.time() // 600) if window is None else window
    return str(int(_hmac(f"setup|{w}")[:10], 16) % 1_000_000).zfill(6)


def check_setup_code(code: str) -> bool:
    w = int(time.time() // 600)
    return any(hmac.compare_digest((code or "").strip(), setup_code(x)) for x in (w, w - 1))


def set_pin(pin: str) -> None:
    if not re.fullmatch(r"\d{6,12}|.{8,64}", pin or ""):
        raise VaultError("PIN must be 6-12 digits (or a passphrase of 8+ characters)")
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 200_000)
    store.put("vault/pin", {"s": base64.b64encode(salt).decode(), "h": base64.b64encode(h).decode(), "t": time.time()})
    store.put("vault/lock", {"fails": 0, "until": 0})


def check_pin(pin: str) -> bool:
    lock = store.get("vault/lock", {"fails": 0, "until": 0}) or {"fails": 0, "until": 0}
    if lock.get("until", 0) > time.time():
        raise VaultError(f"too many wrong PINs — locked for {int(lock['until'] - time.time()) // 60 + 1} min")
    rec = store.get("vault/pin", None)
    if not rec:
        raise VaultError("no PIN set yet")
    ok = hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", (pin or "").encode(), base64.b64decode(rec["s"]), 200_000),
                             base64.b64decode(rec["h"]))
    if ok:
        if lock.get("fails"):
            store.put("vault/lock", {"fails": 0, "until": 0})
        return True
    fails = int(lock.get("fails", 0)) + 1
    store.put("vault/lock", {"fails": fails, "until": time.time() + (900 * (2 ** max(0, fails - 5)) if fails >= 5 else 0)})
    return False


def issue_owner_token(hours: float = 12) -> str:
    exp = int(time.time() + hours * 3600)
    return f"{exp}.{_hmac(f'owner|{exp}')[:40]}"


def verify_owner_token(tok: str | None) -> bool:
    if not tok or "." not in tok or not enabled():
        return False
    exp, sig = tok.split(".", 1)
    return exp.isdigit() and int(exp) > time.time() and hmac.compare_digest(sig, _hmac(f"owner|{exp}")[:40])


# ---------------------------------------------------------------- web ↔ Telegram link codes
def link_code(chat_id: int | str) -> str:
    """Code a Telegram user pastes into the web app so reminders from the web arrive in their Telegram."""
    cid = str(int(chat_id))
    return f"{base64.b32encode(cid.encode()).decode().rstrip('=')}-{_hmac('link|' + cid)[:8]}".upper()


def parse_link_code(code: str) -> int | None:
    try:
        a, sig = (code or "").strip().upper().split("-", 1)
        cid = base64.b32decode(a + "=" * (-len(a) % 8)).decode()
        if cid.lstrip("-").isdigit() and hmac.compare_digest(sig, _hmac("link|" + cid)[:8].upper()):
            return int(cid)
    except Exception:
        return None
    return None


def link_token(chat_id: int) -> str:
    """Signed token the browser keeps so the server can trust which Telegram chat it may message."""
    return f"{chat_id}.{_hmac(f'tg|{chat_id}')[:32]}"


def verify_link_token(tok: str | None) -> int | None:
    if not tok or "." not in tok:
        return None
    cid, sig = tok.rsplit(".", 1)
    try:
        return int(cid) if hmac.compare_digest(sig, _hmac(f"tg|{int(cid)}")[:32]) else None
    except Exception:
        return None
