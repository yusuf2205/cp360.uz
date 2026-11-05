"""Phone + name sign-in, long-lived device sessions, trusted-network check.

Security model (kept deliberately simple for non-technical staff):
* only people the admin has registered (name + phone) can sign in; there is no self-registration;
* from the office network a registered person gets in at once and the device stays signed in for a year;
* from anywhere else the new device is PENDING until an admin approves it (one tap);
* admins/super-admins never get in by phone from outside: they use the password sign-in;
* every device is a row in user_sessions that an admin can revoke at any time.
"""
import ipaddress
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import User, UserSession
from ..security import make_token


def norm_phone(raw: str | None) -> str | None:
    """'+998 90 123-45-67' / '90 123 45 67' / '998901234567' -> '998901234567'. Returns None if it cannot be a phone."""
    if not raw:
        return None
    d = re.sub(r"\D", "", raw)
    if len(d) == 9:  # local Uzbek number without country code
        d = "998" + d
    if not 10 <= len(d) <= 15:
        return None
    return d


def _tokens(name: str) -> set[str]:
    return {t for t in re.sub(r"[^\w\s]", " ", name.lower().replace("ё", "е")).split() if len(t) >= 2}


def names_match(entered: str, registered: str) -> bool:
    """'Азиз' matches 'Азиз Каримов'; word order does not matter. At least one real word must be shared and nothing foreign added."""
    a, b = _tokens(entered), _tokens(registered)
    return bool(a) and a <= b


def client_ips(request: Request) -> list[str]:
    chain = [x.strip() for x in request.headers.get("x-forwarded-for", "").split(",") if x.strip()]
    if request.client:
        chain.append(request.client.host)
    return chain


_OFFICE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10")]


def _trusted_nets() -> list:
    extra = [ipaddress.ip_network(n.strip(), strict=False) for n in settings.trusted_networks.split(",") if n.strip()]
    return _OFFICE + extra


def is_trusted_network(request: Request) -> bool:
    """True only if EVERY address on the proxy chain is inside the office/private ranges (or TRUSTED_NETWORKS).
    A client cannot fake this by sending its own X-Forwarded-For: the real public address appended by a proxy would
    still be in the chain. (Explicit ranges, not ipaddress.is_private: that also covers documentation ranges.)"""
    ips = client_ips(request)
    if not ips:
        return False
    nets = _trusted_nets()
    for ip in ips:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if not any(a in n for n in nets if a.version == n.version):
            return False
    return True


def device_label(request: Request) -> str:
    ua = request.headers.get("user-agent", "")[:300]
    for key, label in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"), ("Macintosh", "Mac"), ("Linux", "Linux")):
        if key in ua:
            browser = next((b for b in ("Edg", "Chrome", "Firefox", "Safari") if b in ua), "браузер")
            return f"{label} · {'Edge' if browser == 'Edg' else browser}"
    return ua[:60] or "устройство"


def new_session(db: Session, user: User, request: Request, status: str = "ACTIVE") -> UserSession:
    s = UserSession(user_id=user.id, jti=secrets.token_urlsafe(24), poll_secret=secrets.token_urlsafe(24), status=status, device=device_label(request),
                    ip=", ".join(client_ips(request))[:100], expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_days))
    db.add(s)
    db.flush()
    return s


def token_for(s: UserSession) -> str:
    return make_token(s.user_id, s.jti, s.expires_at)


_fails: dict[str, list[float]] = {}


def throttle(key: str, limit: int, window: int = 900):
    now_ = time.time()
    hits = [t for t in _fails.get(key, []) if now_ - t < window]
    if len(hits) >= limit:
        raise HTTPException(429, "Слишком много попыток. Подождите 15 минут и попробуйте снова.")
    _fails[key] = hits


def record_fail(key: str):
    _fails.setdefault(key, []).append(time.time())


def find_user_by_phone(db: Session, phone: str) -> User | None:
    return db.scalar(select(User).where(User.phone == phone))
