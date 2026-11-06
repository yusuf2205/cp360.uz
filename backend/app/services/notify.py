"""Telegram notification to the procurement team when a supplier answers. Optional: silent if not configured."""
import html
import logging

import httpx

from ..config import settings

log = logging.getLogger("notify")


def configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def send_telegram(text: str) -> bool:
    """Best effort: a failed notification must never break the supplier's submission."""
    if not configured():
        return False
    try:
        r = httpx.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage", timeout=10,
                       json={"chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
        if r.status_code != 200:
            log.warning("telegram status %s", r.status_code)  # never log the response body/URL: it contains the token
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        log.warning("telegram failed: %s", type(e).__name__)
        return False


def supplier_answered(number: str, company: str, revision: int, link: str | None) -> None:
    e = html.escape  # supplier text is untrusted: never let it inject markup
    head = "Новый ответ поставщика" if revision == 1 else f"Поставщик исправил ответ (версия {revision})"
    text = f"📥 <b>{head}</b>\nЗакупка: {e(number)}\nПоставщик: {e(company[:120])}"
    if link:
        text += f"\n{e(link)}"
    send_telegram(text)
