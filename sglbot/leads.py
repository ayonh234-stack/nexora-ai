"""Append completed sales leads to a CSV file."""

from __future__ import annotations

import csv
import threading
from datetime import datetime, timezone
from pathlib import Path

LEAD_FIELDS = ("name", "ig_handle", "budget", "contact")
CSV_COLUMNS = [
    "timestamp",
    "telegram_chat_id",
    "telegram_user_id",
    "telegram_username",
    "name",
    "ig_handle",
    "budget",
    "contact",
]

_lock = threading.Lock()


def is_complete(lead: dict) -> bool:
    return all((lead.get(field) or "").strip() for field in LEAD_FIELDS)


def missing_fields(lead: dict) -> list[str]:
    return [field for field in LEAD_FIELDS if not (lead.get(field) or "").strip()]


def append_lead(csv_path: Path, lead: dict) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "telegram_chat_id": lead.get("chat_id") or "",
        "telegram_user_id": lead.get("telegram_user_id") or "",
        "telegram_username": lead.get("telegram_username") or "",
        "name": (lead.get("name") or "").strip(),
        "ig_handle": (lead.get("ig_handle") or "").strip(),
        "budget": (lead.get("budget") or "").strip(),
        "contact": (lead.get("contact") or "").strip(),
    }
    with _lock:
        new_file = not csv_path.exists() or csv_path.stat().st_size == 0
        with csv_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)


def format_admin_notice(lead: dict) -> str:
    username = lead.get("telegram_username") or ""
    handle = f"@{username}" if username else "(none)"
    return (
        "New SocialGrowthLab lead\n"
        f"Name: {lead.get('name') or '-'}\n"
        f"Instagram: {lead.get('ig_handle') or '-'}\n"
        f"Budget: {lead.get('budget') or '-'}\n"
        f"Contact: {lead.get('contact') or '-'}\n"
        f"Telegram: {handle}\n"
        f"User ID: {lead.get('telegram_user_id') or '-'}\n"
        f"Chat ID: {lead.get('chat_id') or '-'}"
    )
