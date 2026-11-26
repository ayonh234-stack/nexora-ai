"""Owner-only encrypted vault (AES-256-GCM, key in VAULT_KEY env). Shared by the web app and the Telegram bot
through the private Blob store. Secrets are only ever decrypted inside tools; they are never shown in chat."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
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



def _pin_item_key(t_ms: int) -> str:
    return f"vault/pin_item/{t_ms}"


def _write_pin(rec: dict | None) -> None:
    """Write pin.json and a unique pin_item so readers are not stuck on a stale overwrite."""
    t_ms = int(time.time() * 1000)
    if rec is None:
        payload = {"cleared": True, "t": t_ms / 1000.0, "t_ms": t_ms}
    else:
        rec = dict(rec)
        rec["t"] = rec.get("t") or (t_ms / 1000.0)
        rec["t_ms"] = t_ms
        payload = rec
    store.put("vault/pin", None if rec is None else payload)
    store.put(_pin_item_key(t_ms), payload)
    # keep the unique log short so list stays cheap
    try:
        keys = store.list_keys("vault/pin_item/")
        for k in keys[:-12]:
            store.delete(k)
    except Exception as exc:
        logging.getLogger(__name__).warning("pin item prune failed: %s", str(exc)[:160])


def _read_pin() -> dict | None:
    cand = []
    try:
        primary = store.get("vault/pin", None)
    except Exception:
        primary = None
    if isinstance(primary, dict) and primary:
        ts = float(primary.get("t_ms") or (float(primary.get("t") or 0) * 1000))
        cand.append((ts, primary))
    try:
        keys = store.list_keys("vault/pin_item/")
    except Exception as exc:
        logging.getLogger(__name__).warning("pin item list failed: %s", str(exc)[:160])
        keys = []
    for k in keys[-20:]:
        try:
            item = store.get(k, None)
        except Exception:
            continue
        if not isinstance(item, dict) or not item:
            continue
        try:
            key_ms = int(k.rsplit("/", 1)[-1])
        except Exception:
            key_ms = 0
        ts = float(item.get("t_ms") or key_ms or (float(item.get("t") or 0) * 1000))
        cand.append((ts, item))
    if not cand:
        return None
    latest = max(cand, key=lambda x: x[0])[1]
    if latest.get("cleared"):
        return None
    if latest.get("s") and latest.get("h"):
        return latest
    return None


def has_pin() -> bool:
    rec = _read_pin()
    return bool(rec and rec.get("s") and rec.get("h"))


# Bengali + Arabic-Indic digits → ASCII, so a code typed as ১২৩৪৫৬ still matches.
_DIGIT_TRANS = str.maketrans("০১২৩৪৫৬৭৮৯٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
SETUP_TTL = 10 * 60  # seconds; codes live in Blob so every serverless instance sees the same set
SETUP_KEEP = 3
BURNED_PINS = frozenset({"521901"})
# Same policy as the Telegram bot: exposed or trivial PINs are rejected.
_WEAK_EXACT = frozenset({"521901", "123456", "654321", "000000", "111111", "123123", "112233", "121212"})


def normalize_digits(text: str) -> str:
    """ASCII-ify digits and strip spaces / hidden characters (iOS OTP autofill often inserts spaces)."""
    s = (text or "").translate(_DIGIT_TRANS)
    return re.sub(r"[\s\-\u200b\u200c\u200d\ufeff,]", "", s)


def is_weak_pin(pin: str) -> bool:
    p = normalize_digits(pin)
    if p in _WEAK_EXACT or p in BURNED_PINS:
        return True
    if p.isdigit() and (len(set(p)) == 1 or p in "01234567890123" or p in "98765432109876"):
        return True
    return False


def _load_setup() -> list[dict]:
    try:
        box = store.get("vault/setup_codes", None)
    except Exception as exc:
        logging.getLogger(__name__).warning("setup index get failed: %s", str(exc)[:160])
        return []
    if not box:
        return []
    try:
        data = _dec(box)
    except Exception as exc:
        logging.getLogger(__name__).warning("setup index decrypt failed: %s", str(exc)[:160])
        return []
    recs = data.get("codes") if isinstance(data, dict) else data
    return list(recs or [])


def _save_setup(recs: list[dict]) -> None:
    store.put("vault/setup_codes", _enc({"codes": recs}))


def _code_item_key(code: str) -> str:
    """Unique, non-overwritten Blob path for one setup code (avoids stale CDN reads of a shared index)."""
    raw = normalize_digits(code)
    digest = hmac.new(_key(), f"setup-item|{raw}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"vault/setup_item/{digest}"


def _put_code_item(code: str, rec: dict) -> None:
    store.put(_code_item_key(code), _enc(rec))


def _get_code_item(code: str, attempts: int = 3) -> dict | None:
    key = _code_item_key(code)
    for i in range(max(1, attempts)):
        try:
            box = store.get(key, None)
        except Exception as exc:
            logging.getLogger(__name__).warning("setup item get failed: %s", str(exc)[:160])
            box = None
        if box:
            try:
                rec = _dec(box)
                if rec:
                    return rec
            except Exception as exc:
                logging.getLogger(__name__).warning("setup item decrypt failed: %s", str(exc)[:160])
        if i + 1 < attempts:
            time.sleep(0.25 * (i + 1))
    return None


def issue_setup_code() -> str:
    """Mint a random 6-digit code. The authoritative copy is a unique Blob object; the last-3 index is best-effort."""
    now = time.time()
    for _ in range(20):
        code = f"{secrets.randbelow(1_000_000):06d}"
        if not is_weak_pin(code):
            break
    rec = {"c": code, "exp": now + SETUP_TTL, "t": now}
    _put_code_item(code, rec)
    got = _get_code_item(code, attempts=5)
    if not got:
        logging.getLogger(__name__).warning("setup item read-back missed after put")
    try:
        recs = [r for r in _load_setup() if float(r.get("exp") or 0) > now]
        recs.append(rec)
        _save_setup(recs[-SETUP_KEEP:])
    except Exception as exc:
        logging.getLogger(__name__).warning("setup index save failed: %s", str(exc)[:160])
    return code


def _legacy_hmac_codes() -> list[str]:
    """v15 issued codes as HMAC(time-window), not Blob. Still accept them for ~20–30 minutes."""
    w = int(time.time() // 600)
    out = []
    for x in (w, w - 1, w - 2):
        out.append(str(int(_hmac(f"setup|{x}")[:10], 16) % 1_000_000).zfill(6))
    return out


def check_setup_code(code: str) -> str:
    """Return 'ok', 'wrong', 'expired', or 'missing' (no code has been issued). Does not consume the code."""
    log = logging.getLogger(__name__)
    raw = normalize_digits(code)
    if not raw:
        log.info("setup-check result=missing unique=skip index_n=- hmac=no reason=empty")
        return "missing"
    now = time.time()
    unique = "miss"
    item = _get_code_item(raw, attempts=3)
    if item:
        c = normalize_digits(str(item.get("c") or ""))
        if len(c) == len(raw) and hmac.compare_digest(c, raw):
            unique = "hit"
            result = "ok" if float(item.get("exp") or 0) > now else "expired"
            log.info("setup-check result=%s unique=%s index_n=- hmac=no", result, unique)
            return result
        unique = "mismatch"

    recs = _load_setup()
    if not recs:
        time.sleep(0.35)
        recs = _load_setup()
    live = [r for r in recs if float(r.get("exp") or 0) > now]

    def _hit(rows: list[dict]) -> bool:
        if len(raw) < 4:
            return False
        for r in rows:
            c = normalize_digits(str(r.get("c") or ""))
            if len(c) == len(raw) and hmac.compare_digest(c, raw):
                return True
        return False

    if _hit(live):
        log.info("setup-check result=ok unique=%s index_n=%s live=%s hmac=no", unique, len(recs), len(live))
        return "ok"
    hmac_hit = False
    if len(raw) == 6:
        for c in _legacy_hmac_codes():
            if hmac.compare_digest(c, raw):
                hmac_hit = True
                break
    if hmac_hit:
        log.info("setup-check result=ok unique=%s index_n=%s live=%s hmac=yes", unique, len(recs), len(live))
        return "ok"
    if _hit(recs):
        log.info("setup-check result=expired unique=%s index_n=%s live=%s hmac=no", unique, len(recs), len(live))
        return "expired"
    result = "missing" if not recs else ("wrong" if live else "expired")
    log.info("setup-check result=%s unique=%s index_n=%s live=%s hmac=no", result, unique, len(recs), len(live))
    return result


def consume_setup_code(code: str) -> None:
    raw = normalize_digits(code)
    try:
        _put_code_item(raw, {"c": raw, "exp": 0, "t": time.time(), "used": True})
    except Exception as exc:
        logging.getLogger(__name__).warning("setup item consume failed: %s", str(exc)[:160])
    kept = []
    for r in _load_setup():
        c = normalize_digits(str(r.get("c") or ""))
        if len(c) == len(raw) and hmac.compare_digest(c, raw):
            continue
        kept.append(r)
    try:
        _save_setup(kept)
    except Exception as exc:
        logging.getLogger(__name__).warning("setup index consume failed: %s", str(exc)[:160])


# Back-compat alias (older callers expected a 6-digit string).
def setup_code(window: int | None = None) -> str:
    return issue_setup_code()


def pin_error_kind(exc: Exception) -> str:
    m = str(exc)
    if "ফাঁস" in m or "exposed" in m.lower():
        return "burned"
    if "সহজ" in m or "weak" in m.lower():
        return "weak"
    if "কমপক্ষে" in m or "সংখ্যা" in m or "6" in m or "digit" in m.lower():
        return "length"
    return "format"


def set_pin(pin: str) -> None:
    pin = normalize_digits(pin)
    if pin in BURNED_PINS or pin == "521901":
        raise VaultError("এই PIN আগে ফাঁস হয়ে গেছে, অন্য একটি নতুন PIN দিন। / This PIN was exposed — choose a different one.")
    if pin.isdigit() and len(pin) < 6:
        raise VaultError(f"PIN কমপক্ষে ৬ সংখ্যার হতে হবে (আপনি {len(pin)} সংখ্যা দিয়েছেন)। / PIN must be at least 6 digits (you entered {len(pin)}).")
    if pin.isdigit() and len(pin) > 12:
        raise VaultError("PIN সর্বোচ্চ ১২ সংখ্যা। / PIN can be at most 12 digits.")
    if is_weak_pin(pin):
        raise VaultError("এই PIN খুব সহজ বা আগে ফাঁস হয়েছিল, অন্য PIN দিন। / This PIN is too weak or was exposed — choose another.")
    if not re.fullmatch(r"\d{6,12}|.{8,64}", pin or ""):
        raise VaultError("PIN হতে হবে ৬–১২ সংখ্যা, অথবা ৮+ অক্ষরের পাসফ্রেজ। / PIN must be 6–12 digits or an 8+ character passphrase.")
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 200_000)
    _write_pin({"s": base64.b64encode(salt).decode(), "h": base64.b64encode(h).decode(), "t": time.time()})
    store.put("vault/lock", {"fails": 0, "until": 0})


def clear_pin() -> None:
    """Remove the web vault PIN (used after a test setup so the owner can set their own)."""
    _write_pin(None)
    store.put("vault/lock", {"fails": 0, "until": 0})
    store.put("vault/setup_codes", _enc({"codes": []}))


def check_pin(pin: str) -> bool:
    lock = store.get("vault/lock", {"fails": 0, "until": 0}) or {"fails": 0, "until": 0}
    if lock.get("until", 0) > time.time():
        raise VaultError(f"too many wrong PINs — locked for {int(lock['until'] - time.time()) // 60 + 1} min")
    rec = _read_pin()
    if not rec:
        raise VaultError("no PIN set yet")
    pin = normalize_digits(pin)
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
