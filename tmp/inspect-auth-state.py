import json
from datetime import datetime, timezone
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User, UserSession, AuditEvent

with SessionLocal() as db:
    users = db.scalars(select(User).order_by(User.email)).all()
    result = {"users": [], "active_sessions": [], "security_events": []}
    now = datetime.now(timezone.utc)
    for user in users:
        result["users"].append({
            "id": user.id, "email": user.email, "role": user.role,
            "is_active": user.is_active, "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "failed_login_count": user.failed_login_count,
            "locked_until": user.locked_until.isoformat() if user.locked_until else None,
        })
        sessions = db.scalars(select(UserSession).where(UserSession.user_id == user.id).order_by(UserSession.created_at.desc())).all()
        for session in sessions:
            result["active_sessions"].append({
                "user_id": user.id, "created_at": session.created_at.isoformat(),
                "expires_at": session.expires_at.isoformat(),
                "is_active": session.expires_at > now,
            })
        events = db.scalars(select(AuditEvent).where(AuditEvent.user_id == user.id).order_by(AuditEvent.created_at.desc()).limit(40)).all()
        for event in events:
            if any(token in (event.event_type or "").lower() for token in ("login", "logout", "password", "user_")):
                result["security_events"].append({
                    "id": event.id, "event_type": event.event_type, "entity_type": event.entity_type,
                    "entity_id": event.entity_id, "created_at": event.created_at.isoformat(),
                    "before_keys": sorted((event.before_json or {}).keys()),
                    "after_keys": sorted((event.after_json or {}).keys()),
                    "metadata_keys": sorted((event.request_metadata or {}).keys()),
                })
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
