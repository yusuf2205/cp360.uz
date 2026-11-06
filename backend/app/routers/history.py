"""History of prices and item names from earlier procurements: autocomplete and "what did we pay last time".

Text matching is done in Python (casefold) over the most recent rows: SQLite lower() ignores Cyrillic, and an
office-sized history is small, so this behaves identically in dev and in PostgreSQL.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require, visible_filter
from ..models import Item, Offer, OfferLine, Procurement, Supplier, User

router = APIRouter(prefix="/api/history", tags=["history"])
SCAN = 3000


def _hit(q: str, text: str | None) -> bool:
    return q.strip().casefold() in (text or "").casefold()


@router.get("/items")
def item_suggestions(q: str = Query("", max_length=100), db: Session = Depends(get_db), user: User = Depends(require("view"))):
    """Item names used before (newest first, one entry per name+unit+specs) so a repeated purchase is two clicks, not retyping."""
    if len(q.strip()) < 2:
        return []
    rows = db.execute(select(Item).join(Procurement, Procurement.id == Item.procurement_id).where(visible_filter(user)).order_by(Item.id.desc()).limit(SCAN)).scalars()
    seen, out = set(), []
    for it in rows:
        key = (it.name.casefold(), it.unit, it.specs or "", it.code or "")
        if key in seen or not _hit(q, it.name):
            continue
        seen.add(key)
        out.append({"name": it.name, "unit": it.unit, "specs": it.specs, "code": it.code, "manufacturer": it.manufacturer})
        if len(out) == 8:
            break
    return out


@router.get("/prices")
def price_history(q: str = Query("", max_length=100), db: Session = Depends(get_db), user: User = Depends(require("view"))):
    """Every confirmed price we were offered for an item, as the supplier stated it.

    Prices are returned raw with their currency and VAT flag: they are NOT averaged or compared here, because mixing
    currencies or with/without-VAT prices would give a misleading number.
    """
    if len(q.strip()) < 2:
        return []
    rows = db.execute(
        select(OfferLine, Offer, Supplier, Procurement, Item)
        .join(Offer, Offer.id == OfferLine.offer_id)
        .join(Supplier, Supplier.id == Offer.supplier_id)
        .join(Procurement, Procurement.id == Offer.procurement_id)
        .join(Item, Item.id == OfferLine.item_id)
        .where(visible_filter(user), OfferLine.unit_price.is_not(None), Offer.status == "CONFIRMED", OfferLine.match_status.in_(("CONFIRMED", "ANALOG_APPROVED")))
        .order_by(Offer.id.desc()).limit(SCAN)
    ).all()
    out = []
    for ln, o, s, p, it in rows:
        if not _hit(q, it.name):
            continue
        out.append({
            "item": it.name, "unit": it.unit, "supplier": s.name, "supplier_id": s.id,
            "unit_price": format(ln.unit_price.normalize(), "f"), "currency": o.currency, "prices_include_vat": o.prices_include_vat,
            "vat_rate": format(o.vat_rate.normalize(), "f") if o.vat_rate is not None else None,
            "date": o.offer_date, "procurement_id": p.id, "procurement": p.number,
        })
        if len(out) == 60:
            break
    return out
