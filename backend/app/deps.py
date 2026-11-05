from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, Procurement, Role, Status, User, UserSession
from .security import decode_token

ALL = "*"
ROLE_PERMS: dict[str, set[str]] = {
    Role.SUPER_ADMIN.value: {ALL},
    Role.ADMIN.value: {"view", "procurement.create", "procurement.edit", "supplier.manage", "import.upload", "review", "approve", "export", "user.manage", "analytics"},
    Role.PROCUREMENT_MANAGER.value: {"view", "procurement.create", "procurement.edit", "supplier.manage", "import.upload", "export", "analytics"},
    Role.REVIEWER.value: {"view", "review", "export", "analytics"},
    Role.APPROVER.value: {"view", "approve", "export", "analytics"},
    Role.VIEWER.value: {"view"},
}
SEE_ALL_ROLES = {Role.SUPER_ADMIN.value, Role.ADMIN.value}
EDITABLE = {Status.DRAFT.value, Status.PREPARED.value, Status.RETURNED.value}


def has_perm(user: User, perm: str) -> bool:
    perms = ROLE_PERMS.get(user.role, set()) | set(user.extra_permissions or [])
    return ALL in perms or perm in perms


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not authenticated")
    decoded = decode_token(authorization[7:])
    if not decoded:
        raise HTTPException(401, "Invalid or expired token")
    uid, jti = decoded
    sess = db.scalar(select(UserSession).where(UserSession.jti == jti, UserSession.user_id == uid))
    now_ = datetime.now(timezone.utc)
    if not sess or sess.status != "ACTIVE" or (sess.expires_at.replace(tzinfo=timezone.utc) if sess.expires_at.tzinfo is None else sess.expires_at) < now_:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, uid)
    if not user or not user.active:
        raise HTTPException(401, "Invalid or expired token")
    last = sess.last_seen if sess.last_seen.tzinfo else sess.last_seen.replace(tzinfo=timezone.utc)
    if now_ - last > timedelta(minutes=10):  # cheap "last seen" without a write on every request
        sess.last_seen = now_
        db.commit()
    user._session_id = sess.id  # type: ignore[attr-defined]
    return user


def require(perm: str):
    def dep(user: User = Depends(current_user)) -> User:
        if not has_perm(user, perm):
            raise HTTPException(403, f"Missing permission: {perm}")
        return user

    return dep


def visible_filter(user: User):
    """SQL condition limiting procurements to those a user may see (department scope)."""
    if user.role in SEE_ALL_ROLES or "see_all_departments" in (user.extra_permissions or []):
        return Procurement.id.is_not(None)
    conds = [Procurement.initiator_id == user.id]
    if user.department:
        conds.append(Procurement.department == user.department)
    return or_(*conds)


def get_visible(db: Session, user: User, pid: int) -> Procurement:
    p = db.scalar(select(Procurement).where(Procurement.id == pid, visible_filter(user)))
    if not p:
        raise HTTPException(404, "Procurement not found")  # 404, not 403: do not reveal existence
    return p


def get_editable(db: Session, user: User, pid: int) -> Procurement:
    p = get_visible(db, user, pid)
    if p.status not in EDITABLE:
        raise HTTPException(409, f"Document in status {p.status} is locked; create a new version to change it")
    return p


def audit(db: Session, user: User | None, action: str, entity: str | None = None, entity_id: int | None = None, **detail):
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity=entity, entity_id=entity_id, detail=detail))
