from tests.test_api import setup_proc
from tests.test_rfq import answer, invite


def _accept(client, pm, pid, token, **kw):
    items = client.get(f"/api/procurements/{pid}", headers=pm).json()["items"]
    r = client.post(f"/api/public/rfq/{token}", json=answer(items, ["1000", "2000"], **kw))
    assert r.status_code == 201, r.text
    sub = client.get(f"/api/procurements/{pid}/invitations", headers=pm).json()[0]["submission"]
    assert client.post(f"/api/submissions/{sub['id']}/accept", json={"force_new": True}, headers=pm).status_code == 200
    return client.get(f"/api/procurements/{pid}/comparison", headers=pm).json()["offers"][0], client.get(f"/api/procurements/{pid}/offers", headers=pm).json()[0]


def test_pickup_never_counts_delivery_even_if_a_cost_was_typed(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    tok = invite(client, pm, p["id"])["token"]
    cmp_offer, offer = _accept(client, pm, p["id"], tok, delivery_terms="Самовывоз", delivery_cost="500000", delivery_days=7)
    assert cmp_offer["delivery"] == "0.00" and cmp_offer["total"] == cmp_offer["items_total"]  # 10*1000 + 5*2000 = 20000, nothing added
    assert "delivery_unknown" not in cmp_offer["flags"]
    assert offer["delivery_cost"] == "0.000000" or float(offer["delivery_cost"]) == 0
    assert offer["delivery_days"] == 7  # for pickup this is "ready for collection in N days"


def test_supplier_delivery_with_empty_cost_means_included_in_price(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    tok = invite(client, pm, p["id"])["token"]
    cmp_offer, offer = _accept(client, pm, p["id"], tok, delivery_terms="Доставка поставщиком")
    assert cmp_offer["total"] == cmp_offer["items_total"] and "delivery_unknown" not in cmp_offer["flags"]
    assert "включена в цену" in (offer["notes"] or "")


def test_supplier_delivery_with_a_cost_is_added_to_the_total(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    tok = invite(client, pm, p["id"])["token"]
    cmp_offer, _ = _accept(client, pm, p["id"], tok, delivery_terms="Доставка поставщиком", delivery_cost="1500")
    assert cmp_offer["delivery"] == "1500.00" and cmp_offer["total"] == "21500.00"


def test_carrier_without_a_cost_stays_unknown(client, make_user):
    pm = make_user("pm@example.com", "PROCUREMENT_MANAGER", "Закупки")
    p = setup_proc(client, pm)
    tok = invite(client, pm, p["id"])["token"]
    cmp_offer, _ = _accept(client, pm, p["id"], tok, delivery_terms="Транспортная компания")
    assert "delivery_unknown" in cmp_offer["flags"]
