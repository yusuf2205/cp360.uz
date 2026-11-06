from app.services import notify
from tests.test_api import setup_proc
from tests.test_rfq import answer, invite
from tests.test_rfq_delivery import _accept


def test_history_suggests_old_items_and_shows_raw_prices(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    name = client.get(f"/api/procurements/{p['id']}", headers=pm).json()["items"][0]["name"]
    _accept(client, pm, p["id"], invite(client, pm, p["id"])["token"])

    sug = client.get("/api/history/items", params={"q": name[:4]}, headers=pm).json()
    assert any(s["name"] == name for s in sug)
    assert client.get("/api/history/items", params={"q": "я"}, headers=pm).json() == []  # too short: no scan of everything

    pr = client.get("/api/history/prices", params={"q": name[:4]}, headers=pm).json()
    assert pr and pr[0]["unit_price"] == "1000" and pr[0]["currency"] and "prices_include_vat" in pr[0]
    assert client.get("/api/history/prices", params={"q": "%"}, headers=pm).json() == []  # wildcard is literal


def test_history_respects_department_scope(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    name = client.get(f"/api/procurements/{p['id']}", headers=pm).json()["items"][0]["name"]
    other = make_user("other@example.com", "PROCUREMENT_MANAGER", "Другой отдел")
    assert client.get("/api/history/items", params={"q": name[:4]}, headers=other).json() == []


def test_telegram_message_escapes_supplier_text(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_telegram", lambda t: sent.append(t))
    notify.supplier_answered("ЗК-1", "<b>Evil</b> & Co", 1, None)
    assert "<b>Evil</b>" not in sent[0] and "&lt;b&gt;Evil" in sent[0]


def test_supplier_submit_notifies_only_when_configured(client, make_user, monkeypatch):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    tok = invite(client, pm, p["id"])["token"]
    items = client.get(f"/api/procurements/{p['id']}", headers=pm).json()["items"]
    sent = []
    monkeypatch.setattr(notify, "send_telegram", lambda t: sent.append(t))
    assert client.post(f"/api/public/rfq/{tok}", json=answer(items, ["1000", "2000"])).status_code == 201
    assert sent == []  # not configured -> silent
    monkeypatch.setattr(notify.settings, "telegram_bot_token", "x")
    monkeypatch.setattr(notify.settings, "telegram_chat_id", "1")
    assert client.post(f"/api/public/rfq/{tok}", json=answer(items, ["1000", "2000"])).status_code == 201
    assert len(sent) == 1 and p["number"] in sent[0]


def test_telegram_failure_never_breaks_the_submission(monkeypatch):
    monkeypatch.setattr(notify.settings, "telegram_bot_token", "x")
    monkeypatch.setattr(notify.settings, "telegram_chat_id", "1")

    def boom(*a, **k):
        raise RuntimeError("network down https://api.telegram.org/botSECRET")

    monkeypatch.setattr(notify.httpx, "post", boom)
    assert notify.send_telegram("hi") is False


def test_admin_can_sign_in_by_name_but_staff_cannot(client, make_user):
    from tests.conftest import login  # noqa: F401
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    assert pm
    r = client.post("/api/auth/login", json={"email": "  admin@example.com ", "password": "admin12345"})
    assert r.status_code == 200
    name = r.json()["user"]["name"]
    assert client.post("/api/auth/login", json={"email": name.upper(), "password": "admin12345"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": name, "password": "wrong"}).status_code == 401
    pm_name = client.get("/api/auth/me", headers=pm).json()["name"]
    assert client.post("/api/auth/login", json={"email": pm_name, "password": "whatever-123"}).status_code == 401


def test_change_password_needs_current_and_signs_out_other_devices(client):
    def sign_in(pw="admin12345"):
        r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": pw})
        return r, {"Authorization": "Bearer " + r.json().get("access_token", "")}

    _, here = sign_in()
    _, other = sign_in()
    url = "/api/auth/change-password"
    assert client.post(url, json={"current": "wrong-password", "new": "BrandNew-pass-1"}, headers=here).status_code == 403
    assert client.post(url, json={"current": "admin12345", "new": "short"}, headers=here).status_code == 422
    assert client.post(url, json={"current": "admin12345", "new": "BrandNew-pass-1"}, headers=here).status_code == 204
    assert client.get("/api/auth/me", headers=here).status_code == 200      # this device stays signed in
    assert client.get("/api/auth/me", headers=other).status_code == 401     # the other one is signed out
    assert sign_in("admin12345")[0].status_code == 401
    assert sign_in("BrandNew-pass-1")[0].status_code == 200
