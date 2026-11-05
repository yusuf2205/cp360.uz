import io

from openpyxl import Workbook, load_workbook

from tests.conftest import login


def xlsx_offer(rows, header=("№", "Наименование", "Ед", "Кол-во", "Цена с НДС", "Сумма с НДС")) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["ООО Тест-Металл"])
    ws.append(["ИНН 301234567"])
    ws.append(["Цены с НДС"])
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def setup_proc(client, h, dept="Закупки"):
    p = client.post("/api/procurements", json={"purpose": "Металл для цеха", "department": dept, "currency": "UZS"}, headers=h).json()
    for name, unit, qty in (("Труба 57х3.5 ГОСТ 8732-78", "т", "10"), ("Лист 10 мм ст3 ГОСТ 19903-74", "т", "5")):
        r = client.post(f"/api/procurements/{p['id']}/items", json={"name": name, "unit": unit, "quantity": qty}, headers=h)
        assert r.status_code == 201, r.text
    return p


def supplier(client, h, name, inn=None):
    r = client.post("/api/suppliers", json={"name": name, "inn": inn}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def manual_offer(client, h, pid, sid, prices, **kw):
    items = client.get(f"/api/procurements/{pid}", headers=h).json()["items"]
    lines = [{"raw_name": it["name"], "unit": it["unit"], "quantity": it["quantity"], "unit_price": pr, "item_id": it["id"]} for it, pr in zip(items, prices) if pr]
    r = client.post(f"/api/procurements/{pid}/offers", json={"supplier_id": sid, "currency": "UZS", "prices_include_vat": True, "lines": lines, **kw}, headers=h)
    assert r.status_code == 201, r.text
    o = r.json()
    for ln in o["lines"]:
        r = client.post(f"/api/offer-lines/{ln['id']}/match", json={"item_id": ln["item_id"], "status": "CONFIRMED"}, headers=h)
        assert r.status_code == 200, r.text
    assert client.post(f"/api/offers/{o['id']}/confirm", headers=h).status_code == 200
    return o["id"]


def test_auth_and_permissions(client, admin, make_user):
    assert client.get("/api/procurements").status_code == 401
    assert client.post("/api/auth/login", json={"email": "admin@example.com", "password": "bad"}).status_code == 401
    viewer = make_user("v@example.com", "VIEWER")
    assert client.post("/api/procurements", json={}, headers=viewer).status_code == 403
    assert client.get("/api/procurements", headers=viewer).status_code == 200
    assert client.get("/api/users", headers=viewer).status_code == 403
    assert client.get("/api/audit", headers=viewer).status_code == 403


def test_login_throttle(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}).status_code == 429


def test_department_scoping(client, make_user):
    a = make_user("a@example.com", "PROCUREMENT_MANAGER", "Закупки")
    b = make_user("b@example.com", "PROCUREMENT_MANAGER", "Склад")
    p = setup_proc(client, a)
    assert client.get(f"/api/procurements/{p['id']}", headers=b).status_code == 404
    assert client.get("/api/procurements", headers=b).json() == []
    assert len(client.get("/api/procurements", headers=a).json()) == 1


def test_full_flow_compare_select_approve_export(client, admin, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    rv = make_user("rv@example.com", "REVIEWER", "Закупки")
    ap = make_user("ap@example.com", "APPROVER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    s1, s2, s3 = supplier(client, pm, "Альфа Металл", "111111111"), supplier(client, pm, "Бета Сталь", "222222222"), supplier(client, pm, "Гамма", "333333333")
    o1 = manual_offer(client, pm, pid, s1, ["9500000", "7000000"], delivery_days=5)
    manual_offer(client, pm, pid, s2, ["9800000", "6500000"], delivery_days=10)
    manual_offer(client, pm, pid, s3, ["9000000", None], delivery_days=3)  # incomplete: no price for item 2

    c = client.get(f"/api/procurements/{pid}/comparison", headers=pm).json()
    assert c["cheapest_complete_offer_id"] == o1  # Гамма is cheapest per sum but incomplete
    assert len(c["incomplete_offer_ids"]) == 1
    assert c["split_total"] == "122500000.00"  # 10*9.0m (Gamma) + 5*6.5m (Beta)
    assert c["split_savings_vs_cheapest_complete"] == "7500000.00"  # vs Alfa 130m (Beta is 130.5m)

    # selecting an incomplete offer for the whole purchase is refused
    gamma = [o for o in c["offers"] if o["supplier_name"] == "Гамма"][0]
    r = client.put(f"/api/procurements/{pid}/selection", json={"mode": "single", "supplier_id": gamma["supplier_id"], "reason": "самая низкая цена"}, headers=pm)
    assert r.status_code == 422
    r = client.put(f"/api/procurements/{pid}/selection", json={"mode": "single", "supplier_id": s1, "reason": "Полное предложение, срок поставки подходит"}, headers=pm)
    assert r.status_code == 200

    t = lambda who, to, **kw: client.post(f"/api/procurements/{pid}/transition", json={"to": to, **kw}, headers=who)  # noqa: E731
    assert t(pm, "PREPARED").status_code == 200
    assert t(pm, "IN_REVIEW").status_code == 200
    assert t(pm, "IN_APPROVAL").status_code == 403  # manager has no review permission
    assert t(rv, "IN_APPROVAL").status_code == 200
    assert t(rv, "APPROVED", confirm=True).status_code == 403
    assert t(ap, "APPROVED").status_code == 422  # needs explicit confirmation
    assert t(ap, "APPROVED", confirm=True).status_code == 200

    # approved => locked
    assert client.post(f"/api/procurements/{pid}/items", json={"name": "x", "unit": "шт", "quantity": "1"}, headers=pm).status_code == 409
    assert client.post(f"/api/offers/{o1}/confirm", headers=pm).status_code == 409
    d = client.get("/api/dashboard", headers=ap).json()
    assert d["approved"] == 1 and d["approved_amount_by_currency"]["UZS"] == "130000000.00"  # 10*9.5m + 5*7m
    assert d["confirmed_savings"] is None

    # export
    r = client.get(f"/api/procurements/{pid}/export.xlsx", headers=ap)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Сравнительный лист", "Детализация товаров", "Коммерческие предложения", "Расчёты и курсы", "История согласования"]
    ws = wb["Сравнительный лист"]
    formulas = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")]
    assert any(f.startswith("=$D8*") for f in formulas) and any(f.startswith("=SUM(") for f in formulas)
    assert ws["E6"].value == "Альфа Металл" and ws["E7"].value == "Цена с НДС" and ws["F7"].value == "Сумма с НДС"
    assert "E6:F6" in {str(m) for m in ws.merged_cells.ranges}
    # incomplete supplier: missing price shown as a dash, not 0
    gamma_col = next(c.column for c in ws[6] if c.value == "Гамма")
    assert ws.cell(row=9, column=gamma_col).value == "—"
    assert ws.page_setup.orientation == "landscape" and ws.print_title_rows == "$6:$7"
    h = client.get(f"/api/procurements/{pid}/history", headers=ap).json()
    assert [e["to"] for e in h] == ["PREPARED", "IN_REVIEW", "IN_APPROVAL", "APPROVED"]

    # new version unlocks, with confirmation
    assert client.post(f"/api/procurements/{pid}/new-version", headers=pm).status_code == 422
    assert client.post(f"/api/procurements/{pid}/new-version?confirm=true", headers=pm).json()["version"] == 2


def test_initiator_cannot_approve_own(client, admin, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    ad = make_user("ad@example.com", "ADMIN", "Закупки")
    p = setup_proc(client, ad)
    pid = p["id"]
    sid = supplier(client, ad, "Альфа", "1")
    manual_offer(client, ad, pid, sid, ["1000", "2000"])
    client.put(f"/api/procurements/{pid}/selection", json={"mode": "single", "supplier_id": sid, "reason": "единственное предложение"}, headers=ad)
    for to in ("PREPARED", "IN_REVIEW", "IN_APPROVAL"):
        assert client.post(f"/api/procurements/{pid}/transition", json={"to": to}, headers=ad).status_code == 200
    r = client.post(f"/api/procurements/{pid}/transition", json={"to": "APPROVED", "confirm": True}, headers=ad)
    assert r.status_code == 403


def test_smart_import_xlsx_review_and_apply(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    data = xlsx_offer([(1, "Труба 57х3.5 ГОСТ 8732-78", "т", 10, 9500000, 95000000), (2, "Лист 12 мм ст3 ГОСТ 19903-74", "т", 5, 7000000, 35000000), (3, "Уголок 50х50", "т", 1, None, None)])
    r = client.post("/api/imports", data={"procurement_id": pid}, files=[("files", ("kp.xlsx", data, "application/octet-stream"))], headers=pm)
    assert r.status_code == 202, r.text
    did = r.json()[0]["id"]
    # idempotent: same file again does not create a second document
    r2 = client.post("/api/imports", data={"procurement_id": pid}, files=[("files", ("kp-copy.xlsx", data, "application/octet-stream"))], headers=pm)
    assert r2.json()[0]["id"] == did and r2.json()[0]["duplicate_upload"] is True
    d = client.get(f"/api/imports/{did}", headers=pm).json()
    assert d["status"] == "NEEDS_REVIEW"
    ex = d["extraction"]
    assert len(ex["lines"]) == 3 and ex["supplier"]["inn"] == "301234567" and ex["offer"]["prices_include_vat"] is True
    assert ex["lines"][0]["source"]["row"] == 5 and ex["lines"][0]["source"]["sheet"]
    assert ex["lines"][2]["unit_price"] is None
    sug = d["line_suggestions"]
    assert sug[0]["status"] == "SUGGESTED"
    assert sug[1]["status"] == "TECH_REVIEW" and "numeric_parameters_differ" in sug[1]["flags"]  # 12 mm offered vs 10 mm requested

    lines = [{"name": l["name"], "unit": l["unit"], "quantity": l["quantity"], "unit_price": l["unit_price"], "src_index": i, "item_id": s["item_id"], "confirm_match": i == 0} for i, (l, s) in enumerate(zip(ex["lines"], sug))]
    lines[0]["unit_price"] = "9400000"  # human correction
    r = client.post(f"/api/imports/{did}/apply", json={"new_supplier": {"name": "ООО Тест-Металл", "inn": ex["supplier"]["inn"]}, "offer": {"currency": "UZS", "prices_include_vat": True}, "lines": lines}, headers=pm)
    assert r.status_code == 200, r.text
    off = r.json()
    st = {l["raw_name"][:5]: l for l in off["lines"]}
    assert st["Труба"]["match_status"] == "CONFIRMED" and st["Труба"]["original"]["unit_price"] == "9500000"
    assert st["Лист "]["match_status"] == "TECH_REVIEW"  # not silently equated
    assert off["status"] == "NEEDS_REVIEW"
    assert client.get(f"/api/imports/{did}", headers=pm).json()["status"] == "PROCESSED"

    # comparison: nothing counted for unconfirmed lines, offer is incomplete and not a winner
    c = client.get(f"/api/procurements/{pid}/comparison", headers=pm).json()
    assert c["cheapest_complete_offer_id"] is None and c["incomplete_offer_ids"]
    # explicit analog approval resolves TECH_REVIEW
    lid = st["Лист "]["id"]
    assert client.post(f"/api/offer-lines/{lid}/match", json={"item_id": st["Лист "]["item_id"], "status": "CONFIRMED"}, headers=pm).status_code == 422
    assert client.post(f"/api/offer-lines/{lid}/match", json={"item_id": st["Лист "]["item_id"], "status": "ANALOG_APPROVED"}, headers=pm).status_code == 200

    # a second supplier with the same INN is flagged as a duplicate, not silently created
    r = client.post(f"/api/imports/{did}/apply", json={"new_supplier": {"name": "Тест Металл", "inn": "301234567"}, "lines": []}, headers=pm)
    assert r.status_code == 409 and r.json()["detail"]["duplicates"]


def test_confirmed_offer_prices_not_overwritten_without_consent(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    pid = p["id"]
    sid = supplier(client, pm, "Альфа", "111")
    manual_offer(client, pm, pid, sid, ["1000", "2000"])
    data = xlsx_offer([(1, "Труба 57х3.5 ГОСТ 8732-78", "т", 10, 1100, 11000)])
    did = client.post("/api/imports", data={"procurement_id": pid}, files=[("files", ("a.xlsx", data, "application/octet-stream"))], headers=pm).json()[0]["id"]
    body = {"supplier_id": sid, "lines": [{"name": "Труба 57х3.5 ГОСТ 8732-78", "unit": "т", "quantity": "10", "unit_price": "1100"}]}
    assert client.post(f"/api/imports/{did}/apply", json=body, headers=pm).status_code == 409
    assert client.post(f"/api/imports/{did}/apply", json={**body, "allow_overwrite": True}, headers=pm).status_code == 200


def test_upload_rejects_malicious_and_unconfigured_ocr_is_reported(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    r = client.post("/api/imports", data={"procurement_id": p["id"]}, files=[("files", ("invoice.pdf", b"MZ\x90\x00" + b"\x00" * 100, "application/pdf"))], headers=pm)
    assert r.status_code == 202 and "error" in r.json()[0]  # extension says pdf, content is an executable
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    r = client.post("/api/imports", data={"procurement_id": p["id"]}, files=[("files", ("photo.png", png, "image/png"))], headers=pm)
    d = client.get(f"/api/imports/{r.json()[0]['id']}", headers=pm).json()
    assert d["status"] == "ERROR" and "OCR" in d["error"]  # honest failure, no fabricated data


def test_pasted_text_import(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    text = 'ООО "Металл-Снаб"\nКоммерческое предложение № 7 от 01.11.2026\nТруба 57х3.5 ГОСТ 8732-78 10 т х 9 400 000'
    r = client.post("/api/imports", data={"procurement_id": p["id"], "text": text}, headers=pm)
    d = client.get(f"/api/imports/{r.json()[0]['id']}", headers=pm).json()
    assert d["status"] == "NEEDS_REVIEW" and d["extraction"]["lines"][0]["unit_price"] == "9400000"


def test_corrections_are_logged(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    sid = supplier(client, pm, "Альфа", "111")
    oid = manual_offer(client, pm, p["id"], sid, ["1000", "2000"])
    lid = client.get(f"/api/procurements/{p['id']}/offers", headers=pm).json()[0]["lines"][0]["id"]
    r = client.put(f"/api/offer-lines/{lid}", json={"raw_name": "Труба 57х3.5 ГОСТ 8732-78", "unit": "т", "quantity": "10", "unit_price": "1200", "item_id": None}, headers=pm)
    assert r.status_code == 200 and float(r.json()["original"]["unit_price"]) == 1000
    assert client.get(f"/api/procurements/{p['id']}/offers", headers=pm).json()[0]["status"] == "NEEDS_REVIEW"  # edit invalidates confirmation


def test_zero_price_rejected(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    sid = supplier(client, pm, "Альфа", "111")
    r = client.post(f"/api/procurements/{p['id']}/offers", json={"supplier_id": sid, "lines": [{"raw_name": "x", "unit_price": "0"}]}, headers=pm)
    assert r.status_code == 422


def test_supplier_duplicate_detection(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    supplier(client, pm, 'ООО "Альфа Металл"', "111")
    assert client.post("/api/suppliers", json={"name": "Альфа металл", "inn": None}, headers=pm).status_code == 409
    assert client.post("/api/suppliers", json={"name": "Другая", "inn": "111"}, headers=pm).status_code == 409
    assert client.post("/api/suppliers?force=true", json={"name": "Другая", "inn": "111"}, headers=pm).status_code == 201


def test_unwritable_storage_gives_clear_error_and_unhealthy_status(client, make_user, monkeypatch, tmp_path):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    from app.services import pipeline

    def boom(data):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(pipeline, "store_bytes", boom)
    r = client.post("/api/imports", data={"procurement_id": p["id"]}, files=[("files", ("a.txt", b"hello world", "text/plain"))], headers=pm)
    assert r.status_code == 503 and "хранилище" in r.json()["detail"].lower()
    from app.config import settings
    blocker = tmp_path / "file"
    blocker.write_text("x")  # a directory cannot be created below a regular file, on any OS
    monkeypatch.setattr(settings, "storage_dir", str(blocker / "sub"))
    assert client.get("/api/health").status_code == 503
