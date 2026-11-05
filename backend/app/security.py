import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        s, d = stored.split("$")
        dk = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2**14, r=8, p=1)
        return hmac.compare_digest(dk, base64.b64decode(d))
    except Exception:
        return False


def make_token(user_id: int, jti: str, expires: datetime) -> str:
    return jwt.encode({"sub": str(user_id), "jti": jti, "exp": expires}, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> tuple[int, str] | None:
    try:
        d = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return int(d["sub"]), str(d["jti"])
    except Exception:
        return None
