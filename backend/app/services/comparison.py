"""Comparison engine. Pure functions over plain data, all money in Decimal.

Rules (from the spec):
* a missing price is None, never 0, and makes the offer incomplete;
* prices are normalised to "with VAT" in the procurement currency before comparing;
* an offer with unknown VAT basis / missing FX rate / unconfirmed line matching is not comparable;
* the lowest sum of an incomplete offer never wins;
* delivery is only distributed over items by an explicit rule.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

CONFIRMED_MATCH = {"CONFIRMED", "ANALOG_APPROVED"}
D0 = Decimal(0)
D100 = Decimal(100)


def D(v) -> Decimal | None:
    if v is None or v == "":
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def money(v: Decimal | None, places: int = 2) -> str | None:
    if v is None:
        return None
    return str(v.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


@dataclass
class ItemIn:
    id: int
    name: str
    unit: str
    quantity: Decimal


@dataclass
class LineIn:
    item_id: int | None
    unit_price: Decimal | None
    match_status: str
    quantity: Decimal | None = None
    unit: str | None = None


@dataclass
class OfferIn:
    id: int
    supplier_id: int
    supplier_name: str
    currency: str
    prices_include_vat: bool | None
    vat_rate: Decimal | None
    discount_pct: Decimal | None
    delivery_cost: Decimal | None
    delivery_days: int | None
    lines: list[LineIn] = field(default_factory=list)
    status: str = "CONFIRMED"


def fx_factor(offer_cur: str, base_cur: str, rates: dict) -> Decimal | None:
    if offer_cur == base_cur:
        return Decimal(1)
    r = rates.get(offer_cur)
    return D(r.get("rate")) if r and D(r.get("rate")) else None


def normalise_unit_price(line: LineIn, o: OfferIn, factor: Decimal) -> tuple[Decimal | None, list[str]]:
    """Unit price WITH VAT in base currency, after discount. Returns (price|None, issues)."""
    issues: list[str] = []
    p = line.unit_price
    if p is None:
        return None, ["price_missing"]
    if o.prices_include_vat is None:
        return None, ["vat_basis_unknown"]
    if not o.prices_include_vat:
        if o.vat_rate is None:
            return None, ["vat_rate_missing"]
        p = p * (1 + o.vat_rate / D100)
    if o.discount_pct:
        p = p * (1 - o.discount_pct / D100)
    return p * factor, issues


def compare(
    items: Iterable[ItemIn],
    offers: Iterable[OfferIn],
    base_currency: str,
    rates: dict,
    delivery_rule: str = "none",  # none | by_value
    need_days: int | None = None,
) -> dict:
    items = list(items)
    offers = list(offers)
    result_offers = []
    # per item -> list of (supplier_id, unit_price, sum)
    per_item: dict[int, list[dict]] = {i.id: [] for i in items}

    for o in offers:
        factor = fx_factor(o.currency, base_currency, rates)
        flags: list[str] = []
        if factor is None:
            flags.append(f"fx_rate_missing:{o.currency}")
        if o.status != "CONFIRMED":
            flags.append("offer_not_confirmed")
        cells: dict[int, dict] = {}
        for it in items:
            lines = [l for l in o.lines if l.item_id == it.id]
            cell: dict = {"unit_price": None, "sum": None, "status": "absent", "issues": []}
            if not lines:
                cells[it.id] = cell
                continue
            line = lines[0]
            if len(lines) > 1:
                cell["issues"].append("duplicate_lines")
            if line.match_status not in CONFIRMED_MATCH:
                cell.update(status="unconfirmed_match", issues=cell["issues"] + [f"match:{line.match_status}"])
                cells[it.id] = cell
                continue
            if factor is None:
                cell.update(status="no_rate")
                cells[it.id] = cell
                continue
            price, issues = normalise_unit_price(line, o, factor)
            cell["issues"] += issues
            if price is None:
                cell["status"] = "price_unusable"
            else:
                cell.update(status="ok", unit_price=price, sum=it.quantity * price)
                if line.quantity is not None and line.quantity != it.quantity:
                    cell["issues"].append("quantity_differs")
                if line.unit and line.unit.strip().lower() != it.unit.strip().lower():
                    cell["issues"].append("unit_differs")
            cells[it.id] = cell

        ok_cells = [c for c in cells.values() if c["status"] == "ok"]
        items_total = sum((c["sum"] for c in ok_cells), D0)
        complete = len(ok_cells) == len(items) and len(items) > 0 and not any(
            f.startswith("fx_rate") or f == "offer_not_confirmed" for f in flags
        )
        delivery = None
        if o.delivery_cost is not None and factor is not None:
            delivery = o.delivery_cost * factor  # delivery assumed as stated; VAT on delivery is not guessed
        else:
            if o.delivery_cost is None:
                flags.append("delivery_unknown")
        if delivery_rule == "by_value" and delivery and items_total:
            for c in ok_cells:
                c["delivery_share"] = delivery * c["sum"] / items_total
        late = bool(need_days is not None and o.delivery_days is not None and o.delivery_days > need_days)
        if late:
            flags.append("delivery_too_late")
        if o.delivery_days is None:
            flags.append("delivery_days_unknown")
        result_offers.append(
            {
                "offer_id": o.id,
                "supplier_id": o.supplier_id,
                "supplier_name": o.supplier_name,
                "cells": cells,
                "items_total": items_total,
                "delivery": delivery,
                "total": items_total + (delivery or D0),
                "complete": complete,
                "missing_items": [i.id for i in items if cells[i.id]["status"] != "ok"],
                "flags": flags,
                "delivery_days": o.delivery_days,
            }
        )
        for it in items:
            c = cells[it.id]
            if c["status"] == "ok":
                per_item[it.id].append({"supplier_id": o.supplier_id, "unit_price": c["unit_price"], "sum": c["sum"]})

    best_per_item = {}
    for it in items:
        cand = per_item[it.id]
        if cand:
            best = min(cand, key=lambda x: x["unit_price"])
            best_per_item[it.id] = {**best, "tied": [c["supplier_id"] for c in cand if c["unit_price"] == best["unit_price"]]}

    complete_offers = [r for r in result_offers if r["complete"]]
    cheapest = min(complete_offers, key=lambda r: r["total"]) if complete_offers else None
    split_total = None
    split_complete = bool(items) and all(i.id in best_per_item for i in items)
    if split_complete:
        split_total = sum((best_per_item[i.id]["sum"] for i in items), D0)
    savings = None
    if cheapest and split_total is not None:
        savings = max(cheapest["items_total"] - split_total, D0)
    for r in result_offers:
        r["diff_vs_cheapest_pct"] = (
            (r["total"] - cheapest["total"]) / cheapest["total"] * D100 if cheapest and r["complete"] and cheapest["total"] else None
        )
    return {
        "currency": base_currency,
        "vat_basis": "with_vat",
        "delivery_rule": delivery_rule,
        "offers": result_offers,
        "best_per_item": best_per_item,
        "cheapest_complete_offer_id": cheapest["offer_id"] if cheapest else None,
        "split_total": split_total,
        "split_savings_vs_cheapest_complete": savings,
        "incomplete_offer_ids": [r["offer_id"] for r in result_offers if not r["complete"]],
    }


def serialise(res: dict) -> dict:
    """Decimals -> strings (2 places for money, exact for ratios) for JSON/API output."""
    def conv(v):
        if isinstance(v, Decimal):
            return money(v, 2)
        if isinstance(v, dict):
            return {str(k): conv(x) for k, x in v.items()}
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v

    return conv(res)
