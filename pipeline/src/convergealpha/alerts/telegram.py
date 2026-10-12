"""Optional phone alerts through a Telegram bot. Disabled unless TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID are both set. The token travels in the URL path, so errors are redacted."""

from __future__ import annotations

from collections.abc import Mapping

from convergealpha.config import secret
from convergealpha.util import http
from convergealpha.util.log import get

log = get(__name__)


def enabled(env: Mapping[str, str]) -> bool:
    return bool(secret("TELEGRAM_BOT_TOKEN", env) and secret("TELEGRAM_CHAT_ID", env))


def send(text: str, env: Mapping[str, str]) -> bool:
    token, chat = secret("TELEGRAM_BOT_TOKEN", env), secret("TELEGRAM_CHAT_ID", env)
    if not token or not chat:
        return False
    s = http.make_session(retries=2)
    try:
        r = s.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True},
            timeout=20,
        )
        if r.status_code != 200:
            log.warning("telegram: HTTP %d", r.status_code)
            return False
        return True
    except Exception as e:
        log.warning("telegram failed: %s", type(e).__name__)
        return False


def send_many(lines: list[str], env: Mapping[str, str], title: str = "ConvergeAlpha") -> int:
    if not lines or not enabled(env):
        return 0
    body = f"{title}\n" + "\n".join(f"• {x}" for x in lines[:40])
    return 1 if send(body, env) else 0
