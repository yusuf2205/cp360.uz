from datetime import timedelta

import pytest

from app.db import SessionLocal
from app.models import UserSession
from app.services import sessions as S

LAN = {"X-Forwarded-For": "192.168.1.50"}
OUTSIDE = {"X-Forwarded-For": "203.0.113.9"}


def add_staff(client, admin, name="Азиз Каримов", phone="+998 90 123 45 67", role="PROCUREMENT_MANAGER"):
    r = client.post("/api/users", json={"name": name, "phone": phone, "role": role}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def phone_login(client, name, phone, headers=LAN):
    return client.post("/api/auth/phone-login", json={"name": name, "phone": phone}, headers=headers)


def test_phone_formats_normalise():
    for raw in ("+998 90 123 45 67", "90 123 45 67", "998901234567", "+998(90)123-45-67", "901234567"):
        assert S.norm_phone(raw) == "998901234567", raw
    assert S.norm_phone("123") is None and S.norm_phone("") is None and S.norm_phone(None) is None


def test_name_matching_is_forgiving_but_not_open():
    assert S.names_match("Азиз", "Азиз Каримов") and S.names_match("каримов азиз", "Азиз Каримов") and S.names_match("АЗИЗ  каримов", "Азиз Каримов")
    assert not S.names_match("Бобур", "Азиз Каримов") and not S.names_match("Азиз Петров", "Азиз Каримов") and not S.names_match("", "Азиз Каримов")


def test_staff_signs_in_once_from_office_and_stays_signed_in(client, admin):
    add_staff(client, admin)
    r = phone_login(client, "Азиз", "90 123 45 67")
    assert r.status_code == 200, r.text
    tok = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.get("/api/auth/me", headers=tok).json()["name"] == "Азиз Каримов"
    assert client.get("/api/procurements", headers=tok).status_code == 200
    with SessionLocal() as db:  # a year-long session: no re-login needed
        s = db.query(UserSession).filter(UserSession.status == "ACTIVE").order_by(UserSession.id.desc()).first()
        assert (s.expires_at.replace(tzinfo=None) - s.created_at.replace(tzinfo=None)) > timedelta(days=300)


def test_wrong_name_or_unknown_phone_get_the_same_vague_error(client, admin):
    add_staff(client, admin)
    a = phone_login(client, "Бобур", "+998 90 123 45 67")
    b = phone_login(client, "Азиз", "+998 91 000 00 00")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()
    assert phone_login(client, "Азиз", "12").status_code == 422


def test_switched_off_employee_loses_all_devices_immediately(client, admin):
    u = add_staff(client, admin)
    tok = {"Authorization": "Bearer " + phone_login(client, "Азиз", u["phone"]).json()["access_token"]}
    assert client.get("/api/auth/me", headers=tok).status_code == 200
    assert client.patch(f"/api/users/{u['id']}", json={"active": False}, headers=admin).status_code == 200
    assert client.get("/api/auth/me", headers=tok).status_code == 401
    assert phone_login(client, "Азиз", u["phone"]).status_code == 401


def test_outside_network_needs_admin_approval(client, admin):
    u = add_staff(client, admin)
    r = phone_login(client, "Азиз", u["phone"], OUTSIDE)
    assert r.status_code == 200 and r.json()["pending"] is True and "access_token" not in r.json()
    sid, secret = r.json()["session_id"], r.json()["poll_secret"]
    assert client.get(f"/api/auth/device-status?session_id={sid}&secret={secret}").json() == {"status": "PENDING"}
    assert client.get(f"/api/auth/device-status?session_id={sid}&secret=wrong").status_code == 404
    pend = [s for s in client.get("/api/auth/sessions", headers=admin).json() if s["status"] == "PENDING"]
    assert pend and pend[0]["user"] == "Азиз Каримов"
    assert client.post(f"/api/auth/sessions/{sid}/approve", headers=admin).status_code == 200
    st = client.get(f"/api/auth/device-status?session_id={sid}&secret={secret}").json()
    assert st["status"] == "ACTIVE"
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + st["access_token"]}).status_code == 200


def test_denied_device_never_gets_a_token(client, admin):
    u = add_staff(client, admin)
    r = phone_login(client, "Азиз", u["phone"], OUTSIDE).json()
    client.post(f"/api/auth/sessions/{r['session_id']}/deny", headers=admin)
    assert client.get(f"/api/auth/device-status?session_id={r['session_id']}&secret={r['poll_secret']}").json() == {"status": "DENIED"}


def test_spoofed_forwarded_header_cannot_fake_the_office_network(client, admin):
    u = add_staff(client, admin)
    # attacker claims a private address first; the proxy appended the real public one behind it
    r = phone_login(client, "Азиз", u["phone"], {"X-Forwarded-For": "192.168.1.5, 203.0.113.9"})
    assert r.json().get("pending") is True


def test_admins_cannot_phone_login_from_outside(client, admin):
    u = add_staff(client, admin, name="Главный Админ", phone="+998 71 200 00 00", role="ADMIN")
    assert phone_login(client, "Главный", u["phone"], OUTSIDE).status_code == 403
    assert phone_login(client, "Главный", u["phone"], LAN).status_code == 200


def test_employee_cannot_manage_people_or_approve_devices(client, admin):
    u = add_staff(client, admin)
    tok = {"Authorization": "Bearer " + phone_login(client, "Азиз", u["phone"]).json()["access_token"]}
    assert client.get("/api/users", headers=tok).status_code == 403
    assert client.post("/api/users", json={"name": "Хакер Хакеров", "phone": "+998 99 999 99 99"}, headers=tok).status_code == 403
    assert client.post("/api/auth/sessions/1/approve", headers=tok).status_code == 403


def test_logout_revokes_this_device_only(client, admin):
    u = add_staff(client, admin)
    t1 = {"Authorization": "Bearer " + phone_login(client, "Азиз", u["phone"]).json()["access_token"]}
    t2 = {"Authorization": "Bearer " + phone_login(client, "Азиз", u["phone"]).json()["access_token"]}
    assert client.post("/api/auth/logout", headers=t1).status_code == 204
    assert client.get("/api/auth/me", headers=t1).status_code == 401 and client.get("/api/auth/me", headers=t2).status_code == 200


def test_phone_must_be_unique_and_last_super_admin_is_protected(client, admin):
    add_staff(client, admin)
    assert client.post("/api/users", json={"name": "Дубль Дублев", "phone": "90 123 45 67"}, headers=admin).status_code == 409
    me = client.get("/api/auth/me", headers=admin).json()
    assert client.patch(f"/api/users/{me['id']}", json={"active": False}, headers=admin).status_code == 409
    assert client.patch(f"/api/users/{me['id']}", json={"role": "VIEWER"}, headers=admin).status_code == 409


def test_failed_logins_are_throttled(client, admin):
    add_staff(client, admin)
    codes = {phone_login(client, "Бобур", "+998 90 123 45 67").status_code for _ in range(12)}
    assert 429 in codes
    assert phone_login(client, "Азиз", "+998 90 123 45 67").status_code == 429  # locked for this phone for a while


def test_admin_can_edit_their_own_phone_then_use_it(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    assert client.patch(f"/api/users/{me['id']}", json={"name": "Иосиф Админов", "phone": "+998 71 111 22 33"}, headers=admin).status_code == 200
    assert phone_login(client, "Иосиф", "711112233").status_code == 200


@pytest.mark.parametrize("bad", ["", "abc", "12345"])
def test_creating_staff_with_bad_phone_is_rejected(client, admin, bad):
    r = client.post("/api/users", json={"name": "Тест Тестов", "phone": bad}, headers=admin)
    assert r.status_code in (409, 422)
