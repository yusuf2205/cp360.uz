"""Fill a running cp360.uz with a realistic demo purchase (metal products, three suppliers, one open supplier link).

    python scripts/demo_seed.py [http://localhost:8000] [admin@example.com] [admin-password]

Safe to run on a test server only: it creates a new purchase every time.
"""
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
EMAIL = sys.argv[2] if len(sys.argv) > 2 else "admin@example.com"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin12345"

ITEMS = [  # name, unit, quantity
    ("Лист ХК 1,2×1250×2500 ГОСТ 19904-90", "т", "9.5"),
    ("Лист ХК 2,0×1250×2500 ГОСТ 19903-2015", "т", "5.18"),
    ("Лист ГК 4,0×1500×6000 ГОСТ 19903-2015", "т", "1.24"),
    ("Лист ГК 6,0×1500×6000 ГОСТ 19903-2015", "т", "0.58"),
    ("Швеллер 12П ГОСТ 8240-97", "т", "18"),
    ("Уголок 50×50×5 ГОСТ 8509-93", "т", "3"),
]
OFFERS = {  # supplier -> (delivery days, [price per item or None])
    "Металл Индустрия": (5, ["10600000", "10900000", "9900000", "9950000", "10700000", "9800000"]),
    "Molat Trade": (7, ["10500000", "10850000", "9800000", None, "10600000", "9700000"]),
    "Sof metall": (10, ["10450000", "10950000", "9750000", "9900000", "10400000", None]),
}

c = httpx.Client(base_url=BASE, timeout=60)
r = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
r.raise_for_status()
h = {"Authorization": "Bearer " + r.json()["access_token"]}

p = c.post("/api/procurements", json={"purpose": "Металлопрокат для цеха №2", "department": "Закупки", "need_by": "2026-12-15"}, headers=h).json()
for name, unit, qty in ITEMS:
    c.post(f"/api/procurements/{p['id']}/items", json={"name": name, "unit": unit, "quantity": qty}, headers=h).raise_for_status()
items = c.get(f"/api/procurements/{p['id']}", headers=h).json()["items"]

for sup, (days, prices) in OFFERS.items():
    sid = c.post("/api/suppliers", json={"name": sup, "inn": str(300000000 + abs(hash(sup)) % 99999999)}, headers=h)
    sid = sid.json()["id"] if sid.status_code == 201 else c.get("/api/suppliers", params={"q": sup}, headers=h).json()[0]["id"]
    lines = [{"raw_name": it["name"], "unit": it["unit"], "quantity": it["quantity"], "unit_price": pr, "item_id": it["id"]} for it, pr in zip(items, prices) if pr]
    o = c.post(f"/api/procurements/{p['id']}/offers", json={"supplier_id": sid, "prices_include_vat": True, "delivery_days": days, "payment_terms": "Постоплата 10 дн.", "lines": lines}, headers=h).json()
    for ln in o["lines"]:
        c.post(f"/api/offer-lines/{ln['id']}/match", json={"item_id": ln["item_id"], "status": "CONFIRMED"}, headers=h).raise_for_status()
    c.post(f"/api/offers/{o['id']}/confirm", headers=h).raise_for_status()

inv = c.post(f"/api/procurements/{p['id']}/invitations", json={"supplier_name": "Новый поставщик", "valid_days": 7, "vat_rate_default": "12",
                                                              "message": "Цены нужны до пятницы. Доставка до склада в Ташкенте."}, headers=h).json()
print(f"Закупка №{p['id']} ({p['number']}) создана.")
print(f"Ссылка для поставщика: {BASE.replace(':8000', ':3000')}/rfq/{inv['token']}")
