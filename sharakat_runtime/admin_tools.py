"""Account helpers run inside the application environment (subprocess of the CLI).

    python -m sharakat_runtime.admin_tools has-user <email>
    python -m sharakat_runtime.admin_tools reset-password <email>   (new password in SHARAKAT_NEW_PASSWORD)

Uses the application's own password hashing and audit trail, so a reset is
indistinguishable from one made through the API. Prints one JSON object.
"""
from __future__ import annotations

import json
import os
import sys


def main(argv: list[str]) -> int:
    from sqlalchemy import delete, func, select

    from app.database import SessionLocal
    from app.models import User, UserSession
    from app.security import audit, hash_password, utcnow

    command, email = argv[0], argv[1].strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if command == "has-user":
            print(json.dumps({"exists": user is not None, "role": user.role if user else None,
                              "active": bool(user.is_active) if user else None}))
            return 0
        if command != "reset-password":
            raise SystemExit(f"unknown command {command}")
        password = os.environ.get("SHARAKAT_NEW_PASSWORD", "")
        if len(password) < 12:
            raise SystemExit("SHARAKAT_NEW_PASSWORD must contain at least 12 characters")
        created = user is None
        if created:
            user = User(email=email, display_name="Local Administrator", role="admin", is_active=True,
                        failed_login_count=0, created_at=utcnow())
            db.add(user)
        user.password_hash = hash_password(password)
        user.role = "admin"
        user.is_active = True
        user.failed_login_count = 0
        user.locked_until = None
        db.flush()
        revoked = db.execute(delete(UserSession).where(UserSession.user_id == user.id)).rowcount
        audit(db, "LOCAL_ADMIN_PASSWORD_RESET", None, "user", str(user.id),
              after={"email": email, "role": "admin", "created": created, "sessions_revoked": revoked},
              metadata={"origin": "sharakat_runtime reset-admin-password"})
        db.commit()
        print(json.dumps({"status": "created" if created else "reset", "user_id": user.id, "sessions_revoked": revoked}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
