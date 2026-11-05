"""Small production authentication primitives with opaque server-side sessions."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from .database import SessionLocal
from .models import User, UserSession, AuditEvent

SESSION_COOKIE = "alahsa_session"
SESSION_HOURS = 8
_login_attempts: dict[str, list[datetime]] = {}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=128*1024*1024)
    return f"scrypt$32768$8$1${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest_hex)), maxmem=128*1024*1024)
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def session_digest(token: str) -> str:
    secret=os.getenv("SECRET_KEY","development-only-session-key").encode()
    return hmac.new(secret,token.encode(),hashlib.sha256).hexdigest()


def allow_login_attempt(key: str, limit: int = 8, window_seconds: int = 300) -> bool:
    if os.getenv("REDIS_URL"):
        try:
            import redis
            client=redis.Redis.from_url(os.environ["REDIS_URL"],socket_connect_timeout=1,socket_timeout=1)
            redis_key="rate:login:"+hashlib.sha256(key.encode()).hexdigest()
            count=client.incr(redis_key)
            if count==1:client.expire(redis_key,window_seconds)
            return count<=limit
        except Exception:
            if os.getenv("ENVIRONMENT",os.getenv("ENV","development")).lower()=="production":return False
    now = utcnow()
    recent = [item for item in _login_attempts.get(key, []) if (now - item).total_seconds() < window_seconds]
    if len(recent) >= limit:
        _login_attempts[key] = recent
        return False
    recent.append(now)
    _login_attempts[key] = recent
    return True


def allow_rate(key: str, limit: int, window_seconds: int) -> bool:
    if os.getenv("REDIS_URL"):
        try:
            import redis
            client=redis.Redis.from_url(os.environ["REDIS_URL"],socket_connect_timeout=1,socket_timeout=1)
            redis_key="rate:api:"+hashlib.sha256(key.encode()).hexdigest()
            count=client.incr(redis_key)
            if count==1:client.expire(redis_key,window_seconds)
            return count<=limit
        except Exception:
            if os.getenv("ENVIRONMENT",os.getenv("ENV","development")).lower()=="production":return False
    return allow_login_attempt("api:"+key,limit,window_seconds)


def new_session(db, user: User) -> str:
    token = secrets.token_urlsafe(48)
    now = utcnow()
    db.add(UserSession(user_id=user.id, token_hash=session_digest(token),
                       created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=SESSION_HOURS)))
    return token


def user_for_session(token: str | None):
    if not token:
        return None
    digest = session_digest(token)
    with SessionLocal() as db:
        row = db.scalar(select(UserSession).where(UserSession.token_hash == digest, UserSession.expires_at > utcnow()))
        if not row:
            return None
        user = db.get(User, row.user_id)
        if not user or not user.is_active:
            return None
        return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role}


def audit(db, event_type: str, user_id: int | None = None, entity_type: str | None = None,
          entity_id: str | None = None, before: dict | None = None, after: dict | None = None,
          metadata: dict | None = None) -> None:
    db.add(AuditEvent(user_id=user_id, event_type=event_type, entity_type=entity_type,
                      entity_id=entity_id, before_json=before, after_json=after,
                      request_metadata=metadata or {}, created_at=utcnow()))
