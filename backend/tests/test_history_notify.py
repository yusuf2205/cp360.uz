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
