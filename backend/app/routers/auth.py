import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import audit, current_user, has_perm, require
from ..models import Role, User, UserSession
from ..security import hash_password, verify_password
from ..services import sessions as S

router = APIRouter(prefix="/api", tags=["auth"])
ADMIN_ROLES = {Role.ADMIN.value, Role.SUPER_ADMIN.value}


class LoginIn(BaseModel):
    email: str
    password: str


class PhoneLoginIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=5, max_length=40)


class UserIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    phone: str | None = None
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=10)
    role: Role = Role.PROCUREMENT_MANAGER
    department: str | None = None
    extra_permissions: list[str] = []


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = None
    role: Role | None = None
    department: str | None = None
    active: bool | None = None


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "phone": u.phone, "email": u.email, "role": u.role, "department": u.department,
            "extra_permissions": u.extra_permissions, "active": u.active}


def _ip_key(request: Request) -> str:
    ips = S.client_ips(request)
    return ips[0] if ips else "unknown"


# ---------- sign in ----------
@router.post("/auth/login")
def password_login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    """Break-glass / administrator sign-in with e-mail and password."""
    ident = body.email.strip()
    key = "pw:" + ident.casefold()
    S.throttle(key, 5)
    if "@" in ident:
        u = db.scalar(select(User).where(User.email == ident.lower()))
    else:  # administrator may also sign in by name; only admins with a password, and only if exactly one matches
        found = [x for x in db.scalars(select(User).where(User.password_hash.is_not(None), User.role.in_(ADMIN_ROLES))) if x.name.strip().casefold() == ident.casefold()]
        u = found[0] if len(found) == 1 else None
    if not u or not u.active or not u.password_hash or not verify_password(body.password, u.password_hash):
        S.record_fail(key)
        audit(db, None, "login_failed", detail={"login": ident.casefold()[:100]})
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    sess = S.new_session(db, u, request)
    audit(db, u, "login", detail={"method": "password"})
    db.commit()
    return {"access_token": S.token_for(sess), "token_type": "bearer", "user": user_out(u)}


@router.post("/auth/phone-login")
def phone_login(body: PhoneLoginIn, request: Request, db: Session = Depends(get_db)):
    phone = S.norm_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Введите номер телефона полностью, например +998 90 123 45 67")
    ip_key, ph_key = "ip:" + _ip_key(request), "ph:" + phone
    S.throttle(ip_key, 40)
    S.throttle(ph_key, 8)
    u = S.find_user_by_phone(db, phone)
    if not u or not u.active or not S.names_match(body.name, u.name):
        S.record_fail(ip_key)
        S.record_fail(ph_key)
        audit(db, None, "phone_login_failed", detail={"phone_tail": phone[-4:]})
        db.commit()
        # one message for every failure: do not reveal which phones are registered
        raise HTTPException(401, "Имя или телефон не найдены. Проверьте данные или обратитесь к администратору.")
    trusted = (not settings.lan_only_instant_login) or S.is_trusted_network(request)
    if u.role in ADMIN_ROLES and not trusted:
        raise HTTPException(403, "Администратор входит из внешней сети только по паролю.")
    if trusted:
        sess = S.new_session(db, u, request)
        audit(db, u, "login", detail={"method": "phone"})
        db.commit()
        return {"access_token": S.token_for(sess), "token_type": "bearer", "user": user_out(u)}
    sess = S.new_session(db, u, request, status="PENDING")
    audit(db, u, "device_request", "session", sess.id)
    db.commit()
    return {"pending": True, "session_id": sess.id, "poll_secret": sess.poll_secret}


@router.get("/auth/device-status")
def device_status(session_id: int, secret: str, request: Request, db: Session = Depends(get_db)):
    S.throttle("poll:" + _ip_key(request), 600, 600)
    S.record_fail("poll:" + _ip_key(request))
    s = db.get(UserSession, session_id)
    if not s or not secrets.compare_digest(s.poll_secret, secret):
        raise HTTPException(404, "Запрос не найден")
    if s.status != "ACTIVE":
        return {"status": s.status}
    return {"status": "ACTIVE", "access_token": S.token_for(s), "user": user_out(db.get(User, s.user_id))}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {**user_out(user), "session_id": getattr(user, "_session_id", None)}


@router.post("/auth/logout", status_code=204)
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(UserSession, getattr(user, "_session_id", 0))
    if s:
        s.status = "REVOKED"
        db.commit()


# ---------- devices ----------
def sess_out(s: UserSession, u: User | None) -> dict:
    return {"id": s.id, "user_id": s.user_id, "user": u.name if u else "?", "phone": u.phone if u else None, "status": s.status, "device": s.device, "ip": s.ip,
            "created_at": s.created_at, "last_seen": s.last_seen}


@router.get("/auth/sessions")
def sessions(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(UserSession, User).join(User, User.id == UserSession.user_id).where(UserSession.status.in_(["ACTIVE", "PENDING"]))
    if not has_perm(user, "user.manage"):
        q = q.where(UserSession.user_id == user.id)
    rows = db.execute(q.order_by(UserSession.status.desc(), UserSession.last_seen.desc()).limit(500)).all()
    return [sess_out(s, u) for s, u in rows]


def _decide(db: Session, admin: User, sid: int, new_status: str, allowed_from: set[str]):
    s = db.get(UserSession, sid)
    if not s or s.status not in allowed_from:
        raise HTTPException(404, "Запрос не найден или уже обработан")
    s.status = new_status
    audit(db, admin, f"device_{new_status.lower()}", "session", sid, user_id=s.user_id)
    db.commit()
    return {"ok": True}


@router.post("/auth/sessions/{sid}/approve")
def approve(sid: int, db: Session = Depends(get_db), admin: User = Depends(require("user.manage"))):
    return _decide(db, admin, sid, "ACTIVE", {"PENDING"})


@router.post("/auth/sessions/{sid}/deny")
def deny(sid: int, db: Session = Depends(get_db), admin: User = Depends(require("user.manage"))):
    return _decide(db, admin, sid, "DENIED", {"PENDING"})


@router.post("/auth/sessions/{sid}/revoke")
def revoke(sid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = db.get(UserSession, sid)
    if not s or (s.user_id != user.id and not has_perm(user, "user.manage")):
        raise HTTPException(404, "Устройство не найдено")
    s.status = "REVOKED"
    audit(db, user, "device_revoked", "session", sid, user_id=s.user_id)
    db.commit()
    return {"ok": True}


# ---------- employees ----------
def _check_phone(db: Session, phone_raw: str | None, exclude: int | None = None) -> str | None:
    if phone_raw in (None, ""):
        return None
    phone = S.norm_phone(phone_raw)
    if not phone:
        raise HTTPException(422, "Телефон указан неверно. Пример: +998 90 123 45 67")
    other = S.find_user_by_phone(db, phone)
    if other and other.id != exclude:
        raise HTTPException(409, f"Этот телефон уже зарегистрирован: {other.name}")
    return phone


@router.get("/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(require("user.manage"))):
    seen = dict(db.execute(select(UserSession.user_id, func.max(UserSession.last_seen)).where(UserSession.status == "ACTIVE").group_by(UserSession.user_id)).all())
    devices = dict(db.execute(select(UserSession.user_id, func.count()).where(UserSession.status == "ACTIVE").group_by(UserSession.user_id)).all())
    return [{**user_out(u), "last_seen": seen.get(u.id), "devices": devices.get(u.id, 0)} for u in db.scalars(select(User).order_by(User.active.desc(), User.name))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), user: User = Depends(require("user.manage"))):
    if body.role == Role.SUPER_ADMIN and user.role != Role.SUPER_ADMIN.value:
        raise HTTPException(403, "Только главный администратор может создать главного администратора")
    phone = _check_phone(db, body.phone)
    if not phone and not (body.email and body.password):
        raise HTTPException(422, "Укажите телефон сотрудника")
    if body.email and db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Эта почта уже зарегистрирована")
    u = User(name=body.name.strip(), phone=phone, email=body.email.lower() if body.email else None, password_hash=hash_password(body.password) if body.password else None,
             role=body.role.value, department=body.department, extra_permissions=body.extra_permissions)
    db.add(u)
    db.flush()
    audit(db, user, "user_create", "user", u.id, role=u.role)
    db.commit()
    return user_out(u)


def _active_super_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == Role.SUPER_ADMIN.value, User.active.is_(True))) or 0


@router.patch("/users/{uid}")
def patch_user(uid: int, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(require("user.manage"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404)
    if u.role == Role.SUPER_ADMIN.value and admin.role != Role.SUPER_ADMIN.value:
        raise HTTPException(403, "Изменять главного администратора может только он сам")
    if body.role == Role.SUPER_ADMIN and admin.role != Role.SUPER_ADMIN.value:
        raise HTTPException(403, "Назначить главного администратора может только главный администратор")
    losing_super = u.role == Role.SUPER_ADMIN.value and ((body.role and body.role != Role.SUPER_ADMIN) or body.active is False)
    if losing_super and _active_super_admins(db) <= 1:
        raise HTTPException(409, "Нельзя убрать последнего главного администратора")
    if body.name:
        u.name = body.name.strip()
    if body.phone is not None:
        u.phone = _check_phone(db, body.phone, exclude=u.id)
    if body.role:
        u.role = body.role.value
    if body.department is not None:
        u.department = body.department or None
    if body.active is not None:
        u.active = body.active
        if not body.active:  # switching someone off signs out every device at once
            for s in db.scalars(select(UserSession).where(UserSession.user_id == u.id, UserSession.status.in_(["ACTIVE", "PENDING"]))):
                s.status = "REVOKED"
    audit(db, admin, "user_update", "user", u.id)
    db.commit()
    return user_out(u)


@router.get("/audit")
def audit_log(limit: int = 200, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..models import AuditLog

    if not has_perm(user, "audit.view") and user.role != Role.SUPER_ADMIN.value:
        raise HTTPException(403, "Missing permission: audit.view")
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000)))
    return [{"id": a.id, "user_id": a.user_id, "action": a.action, "entity": a.entity, "entity_id": a.entity_id, "detail": a.detail, "at": a.at} for a in rows]
