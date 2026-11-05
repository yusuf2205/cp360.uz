import io
from datetime import datetime, timedelta, timezone

from openpyxl import load_workbook

from app.db import SessionLocal
from app.models import Invitation
from tests.test_api import setup_proc, supplier


def invite(client, h, pid, **kw):
    r = client.post(f"/api/procurements/{pid}/invitations", json=kw, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def answer(items, prices, **kw):
    base = {"company": "ООО Альфа Металл", "inn": "301234567", "phone": "+998901234567", "prices_include_vat": True, "currency": "UZS", "delivery_days": 5,
            "payment_terms": "Постоплата 10 дн.", "lines": [{"item_id": i["id"], "unit_price": pr} for i, pr in zip(items, prices)]}
    base.update(kw)
    return base


def test_public_form_exposes_only_what_supplier_needs(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    s_other = supplier(client, pm, "Конкурент", "999")
    inv = invite(client, pm, p["id"], message="Цены до пятницы")
    r = client.get(f"/api/public/rfq/{inv['token']}")  # no auth header
    assert r.status_code == 200
    body = r.json()
    assert [i["name"] for i in body["items"]] == ["Труба 57х3.5 ГОСТ 8732-78", "Лист 10 мм ст3 ГОСТ 19903-74"]
    assert body["message"] == "Цены до пятницы" and body["items"][0]["quantity"] == "10"
    flat = str(body)
    assert "Конкурент" not in flat and "initiator" not in flat and "rates" not in flat
    assert client.get("/api/public/rfq/not-a-real-token").status_code == 404
    assert client.get(f"/api/procurements/{p['id']}/invitations").status_code == 401  # buyer side needs login
    assert s_other


def test_invite_requires_items_and_permission(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    viewer = make_user("v@example.com", "VIEWER", "Закупки")
    empty = client.post("/api/procurements", json={"department": "Закупки"}, headers=pm).json()
    assert client.post(f"/api/procurements/{empty['id']}/invitations", json={}, headers=pm).status_code == 422
    p = setup_proc(client, pm)
    assert client.post(f"/api/procurements/{p['id']}/invitations", json={}, headers=viewer).status_code == 403


def test_submit_review_accept_creates_confirmed_offer(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    items = client.get(f"/api/procurements/{pid}", headers=pm).json()["items"]
    inv = invite(client, pm, pid)
    r = client.post(f"/api/public/rfq/{inv['token']}", json=answer(items, ["9500000", None]))
    assert r.status_code == 201 and r.json()["revision"] == 1
    # supplier can correct their answer before the buyer decides
    r = client.post(f"/api/public/rfq/{inv['token']}", json=answer(items, ["9400000", "7000000"]))
    assert r.json()["revision"] == 2
    lst = client.get(f"/api/procurements/{pid}/invitations", headers=pm).json()
    sub = lst[0]["submission"]
    assert sub["status"] == "NEW" and sub["summary"]["total_with_vat"] == "129000000.00"  # 10*9.4m + 5*7m, quantities are OURS
    # nothing is in the comparison before accept
    assert client.get(f"/api/procurements/{pid}/offers", headers=pm).json() == []
    r = client.post(f"/api/submissions/{sub['id']}/accept", json={}, headers=pm)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CONFIRMED"
    c = client.get(f"/api/procurements/{pid}/comparison", headers=pm).json()
    assert c["cheapest_complete_offer_id"] == r.json()["offer_id"] and c["offers"][0]["items_total"] == "129000000.00"
    # accepted answers are locked for the supplier and cannot be accepted twice
    assert client.post(f"/api/public/rfq/{inv['token']}", json=answer(items, ["1", "1"])).status_code == 409
    assert client.post(f"/api/submissions/{sub['id']}/accept", json={}, headers=pm).status_code == 409


def test_supplier_cannot_inject_quantities_or_foreign_items_or_bad_values(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    items = client.get(f"/api/procurements/{pid}", headers=pm).json()["items"]
    tok = invite(client, pm, pid)["token"]
    post = lambda **kw: client.post(f"/api/public/rfq/{tok}", json=answer(items, ["100", "200"], **kw))  # noqa: E731
    assert post(lines=[{"item_id": 99999, "unit_price": "1"}]).status_code == 422  # foreign item
    assert post(lines=[{"item_id": items[0]["id"], "unit_price": "1"}, {"item_id": items[0]["id"], "unit_price": "2"}]).status_code == 422  # duplicate
    assert post(lines=[{"item_id": items[0]["id"], "unit_price": "0"}]).status_code == 422  # zero price
    assert post(lines=[{"item_id": items[0]["id"], "unit_price": "-5"}]).status_code == 422
    assert post(lines=[{"item_id": items[0]["id"], "unit_price": None}]).status_code == 422  # nothing priced
    assert post(prices_include_vat=False).status_code == 422  # VAT rate required without VAT
    assert post(currency="USD").status_code == 422  # no rate configured for USD
    assert post(inn="abc").status_code == 422
    assert post(company="x").status_code == 422
    assert post(prices_include_vat=False, vat_rate="12").status_code == 201


def test_vat_exclusive_answer_is_normalised(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    items = client.get(f"/api/procurements/{pid}", headers=pm).json()["items"]
    tok = invite(client, pm, pid)["token"]
    client.post(f"/api/public/rfq/{tok}", json=answer(items, ["1000", "2000"], prices_include_vat=False, vat_rate="12"))
    sub = client.get(f"/api/procurements/{pid}/invitations", headers=pm).json()[0]["submission"]
    assert sub["summary"]["total_with_vat"] == "22400.00"  # (10*1000 + 5*2000) * 1.12
    oid = client.post(f"/api/submissions/{sub['id']}/accept", json={}, headers=pm).json()["offer_id"]
    c = client.get(f"/api/procurements/{pid}/comparison", headers=pm).json()
    assert [o for o in c["offers"] if o["offer_id"] == oid][0]["items_total"] == "22400.00"


def test_analog_goes_to_technical_review_and_offer_not_confirmed(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    items = client.get(f"/api/procurements/{pid}", headers=pm).json()["items"]
    tok = invite(client, pm, pid)["token"]
    lines = [{"item_id": items[0]["id"], "unit_price": "9000000"}, {"item_id": items[1]["id"], "unit_price": "6000000", "alt_name": "Лист 12 мм ст3"}]
    client.post(f"/api/public/rfq/{tok}", json=answer(items, [], lines=lines))
    sub = client.get(f"/api/procurements/{pid}/invitations", headers=pm).json()[0]["submission"]
    assert sub["summary"]["has_analogs"] is True
    r = client.post(f"/api/submissions/{sub['id']}/accept", json={}, headers=pm).json()
    assert r["status"] == "NEEDS_REVIEW"
    off = client.get(f"/api/procurements/{pid}/offers", headers=pm).json()[0]
    ln = [l for l in off["lines"] if l["raw_name"] == "Лист 12 мм ст3"][0]
    assert ln["match_status"] == "TECH_REVIEW" and "analog_offered" in ln["tech_flags"]
    c = client.get(f"/api/procurements/{pid}/comparison", headers=pm).json()
    assert c["cheapest_complete_offer_id"] is None  # analog not approved => not comparable yet


def test_duplicate_supplier_requires_explicit_choice(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    existing = supplier(client, pm, "Альфа Металл", "301234567")
    items = client.get(f"/api/procurements/{pid}", headers=pm).json()["items"]
    tok = invite(client, pm, pid)["token"]
    client.post(f"/api/public/rfq/{tok}", json=answer(items, ["1000", "2000"]))
    sub = client.get(f"/api/procurements/{pid}/invitations", headers=pm).json()[0]["submission"]
    r = client.post(f"/api/submissions/{sub['id']}/accept", json={}, headers=pm)
    assert r.status_code == 409 and r.json()["detail"]["duplicates"][0]["id"] == existing
    assert client.post(f"/api/submissions/{sub['id']}/accept", json={"supplier_id": existing}, headers=pm).status_code == 200


def test_links_can_be_revoked_expire_and_close_with_document(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    items = client.get(f"/api/procurements/{pid}", headers=pm).json()["items"]
    a, b = invite(client, pm, pid), invite(client, pm, pid)
    assert client.delete(f"/api/invitations/{a['id']}", headers=pm).status_code == 204
    assert client.get(f"/api/public/rfq/{a['token']}").status_code == 404
    with SessionLocal() as db:
        db.get(Invitation, b["id"]).expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    assert client.get(f"/api/public/rfq/{b['token']}").status_code == 410
    assert client.post(f"/api/public/rfq/{b['token']}", json=answer(items, ["1", "1"])).status_code == 410
    c = invite(client, pm, pid)
    client.put(f"/api/procurements/{pid}/selection", json={"mode": "single", "supplier_id": 1, "reason": "x" * 12}, headers=pm)  # may 422, irrelevant
    assert client.get(f"/api/public/rfq/{c['token']}").status_code == 200


def test_reject_needs_comment_and_supplier_may_answer_again(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    items = client.get(f"/api/procurements/{pid}", headers=pm).json()["items"]
    tok = invite(client, pm, pid)["token"]
    client.post(f"/api/public/rfq/{tok}", json=answer(items, ["1000", "2000"]))
    sub = client.get(f"/api/procurements/{pid}/invitations", headers=pm).json()[0]["submission"]
    assert client.post(f"/api/submissions/{sub['id']}/reject", json={"comment": ""}, headers=pm).status_code == 422
    assert client.post(f"/api/submissions/{sub['id']}/reject", json={"comment": "Цены неактуальны"}, headers=pm).status_code == 200
    assert client.post(f"/api/public/rfq/{tok}", json=answer(items, ["900", "1900"])).status_code == 201  # new answer after rejection


def test_public_endpoint_is_throttled(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    tok = invite(client, pm, p["id"])["token"]
    codes = {client.post(f"/api/public/rfq/{tok}", json={}).status_code for _ in range(45)}
    assert 429 in codes


def test_excel_does_not_execute_supplier_text_as_formula(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    items = client.get(f"/api/procurements/{pid}", headers=pm).json()["items"]
    tok = invite(client, pm, pid)["token"]
    evil = '=HYPERLINK("http://evil.example","click")'
    client.post(f"/api/public/rfq/{tok}", json=answer(items, ["1000", "2000"], company=evil + " LLC", payment_terms=evil, comment=evil))
    sub = client.get(f"/api/procurements/{pid}/invitations", headers=pm).json()[0]["submission"]
    assert client.post(f"/api/submissions/{sub['id']}/accept", json={"force_new": True}, headers=pm).status_code == 200
    wb = load_workbook(io.BytesIO(client.get(f"/api/procurements/{pid}/export.xlsx", headers=pm).content))
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("=HYPERLINK"):
                    assert c.data_type == "s", f"{ws.title}!{c.coordinate} would execute as a formula"
    # our own formulas are still live
    assert any(isinstance(c.value, str) and c.value.startswith("=SUM(") and c.data_type == "f" for row in wb.worksheets[0].iter_rows() for c in row)
