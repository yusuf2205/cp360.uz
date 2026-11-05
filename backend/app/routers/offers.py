from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, get_editable, get_visible, require
from ..models import FieldCorrection, Offer, OfferLine, Procurement, Supplier, User
from ..services import matching

router = APIRouter(prefix="/api", tags=["offers"])


class LineIn(BaseModel):
    raw_name: str = Field(min_length=1)
    unit: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = Field(default=None, gt=0)  # None = unknown; zero is not accepted as a price
    item_id: int | None = None


class OfferFields(BaseModel):
    number: str | None = None
    offer_date: date | None = None
    valid_until: date | None = None
    currency: str = Field(default="UZS", min_length=3, max_length=3)
    prices_include_vat: bool | None = None
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100)
    discount_pct: Decimal | None = Field(default=None, ge=0, le=100)
    delivery_cost: Decimal | None = Field(default=None, ge=0)
    delivery_days: int | None = Field(default=None, ge=0)
    payment_terms: str | None = None
    warranty: str | None = None
    notes: str | None = None


class OfferIn(OfferFields):
    supplier_id: int
    lines: list[LineIn] = []


class MatchIn(BaseModel):
    item_id: int | None
    status: str = Field(pattern="^(CONFIRMED|ANALOG_APPROVED|UNMATCHED)$")


def offer_out(o: Offer) -> dict:
    f = {k: getattr(o, k) for k in OfferFields.model_fields}
    for k in ("vat_rate", "discount_pct", "delivery_cost"):
        f[k] = str(f[k]) if f[k] is not None else None
    return {"id": o.id, "procurement_id": o.procurement_id, "supplier_id": o.supplier_id, "supplier": o.supplier.name, "status": o.status, "document_ids": o.document_ids, **f,
            "lines": [line_out(l) for l in o.lines]}


def line_out(l: OfferLine) -> dict:
    return {"id": l.id, "item_id": l.item_id, "raw_name": l.raw_name, "unit": l.unit, "quantity": str(l.quantity) if l.quantity is not None else None,
            "unit_price": str(l.unit_price) if l.unit_price is not None else None, "match_status": l.match_status, "match_score": l.match_score,
            "tech_flags": l.tech_flags, "confidence": l.confidence, "provenance": l.provenance, "original": l.original}


def apply_match(p: Procurement, line: OfferLine, item_id: int | None = None, confirmed: bool = False):
    """Suggest (or, if the user confirmed, set) the item link. Technical flags always force TECH_REVIEW."""
    cands = [{"id": i.id, "name": i.name, "unit": i.unit, "specs": i.specs} for i in p.items]
    if item_id is not None:
        it = next((i for i in cands if i["id"] == item_id), None)
        if not it:
            raise HTTPException(422, f"Item {item_id} is not in this procurement")
        flags = matching.tech_flags(f"{it['name']} {it['specs'] or ''}", line.raw_name)
        if matching.units_compatible(it["unit"], line.unit) is False:
            flags.append("unit_mismatch")
        line.item_id, line.tech_flags = item_id, flags
        line.match_score = matching.similarity(it["name"], line.raw_name)
        line.match_status = "TECH_REVIEW" if flags else ("CONFIRMED" if confirmed else "SUGGESTED")
        return
    s = matching.suggest(cands, line.raw_name, line.unit)
    line.item_id, line.match_score, line.tech_flags, line.match_status = s["item_id"], s["score"], s["flags"], s["status"]


def _check_dup_supplier_offer(db: Session, pid: int, supplier_id: int):
    return db.scalar(select(Offer).where(Offer.procurement_id == pid, Offer.supplier_id == supplier_id))


@router.post("/procurements/{pid}/offers", status_code=201)
def create_offer(pid: int, body: OfferIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    p = get_editable(db, user, pid)
    if not db.get(Supplier, body.supplier_id):
        raise HTTPException(422, "Unknown supplier")
    if _check_dup_supplier_offer(db, pid, body.supplier_id):
        raise HTTPException(409, "This supplier already has an offer here; edit it or merge documents into it")
    o = Offer(procurement_id=pid, supplier_id=body.supplier_id, status="DRAFT", **body.model_dump(exclude={"supplier_id", "lines"}))
    db.add(o)
    db.flush()
    for ln in body.lines:
        l = OfferLine(offer_id=o.id, raw_name=ln.raw_name, unit=ln.unit, quantity=ln.quantity, unit_price=ln.unit_price)
        apply_match(p, l, ln.item_id)
        db.add(l)
    audit(db, user, "offer_create", "offer", o.id)
    db.commit()
    db.refresh(o)
    return offer_out(o)


@router.get("/procurements/{pid}/offers")
def list_offers(pid: int, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    get_visible(db, user, pid)
    return [offer_out(o) for o in db.scalars(select(Offer).where(Offer.procurement_id == pid))]


def _offer_for_edit(db: Session, user: User, oid: int) -> tuple[Offer, Procurement]:
    o = db.get(Offer, oid)
    if not o:
        raise HTTPException(404)
    return o, get_editable(db, user, o.procurement_id)


def _record(db, user, entity, eid, field, old, new):
    if str(old) != str(new):
        db.add(FieldCorrection(entity=entity, entity_id=eid, field=field, old_value=None if old is None else str(old), new_value=None if new is None else str(new), user_id=user.id))


@router.patch("/offers/{oid}")
def edit_offer(oid: int, body: OfferFields, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    o, _ = _offer_for_edit(db, user, oid)
    for k, v in body.model_dump().items():
        _record(db, user, "offer", oid, k, getattr(o, k), v)
        setattr(o, k, v)
    if o.status == "CONFIRMED":
        o.status = "NEEDS_REVIEW"  # an edit after confirmation requires re-confirmation
    audit(db, user, "offer_edit", "offer", oid)
    db.commit()
    return offer_out(o)


@router.delete("/offers/{oid}", status_code=204)
def delete_offer(oid: int, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    o, _ = _offer_for_edit(db, user, oid)
    audit(db, user, "offer_delete", "offer", oid)
    db.delete(o)
    db.commit()


@router.post("/offers/{oid}/lines", status_code=201)
def add_line(oid: int, body: LineIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    o, p = _offer_for_edit(db, user, oid)
    l = OfferLine(offer_id=o.id, raw_name=body.raw_name, unit=body.unit, quantity=body.quantity, unit_price=body.unit_price)
    apply_match(p, l, body.item_id)
    db.add(l)
    if o.status == "CONFIRMED":
        o.status = "NEEDS_REVIEW"
    audit(db, user, "offer_line_add", "offer", oid)
    db.commit()
    return line_out(l)


@router.put("/offer-lines/{lid}")
def edit_line(lid: int, body: LineIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    l = db.get(OfferLine, lid)
    if not l:
        raise HTTPException(404)
    o, p = _offer_for_edit(db, user, l.offer_id)
    if not l.original:
        l.original = {"raw_name": l.raw_name, "unit": l.unit, "quantity": str(l.quantity) if l.quantity is not None else None,
                      "unit_price": str(l.unit_price) if l.unit_price is not None else None}
    for f in ("raw_name", "unit", "quantity", "unit_price"):
        _record(db, user, "offer_line", lid, f, getattr(l, f), getattr(body, f))
        setattr(l, f, getattr(body, f))
    apply_match(p, l, body.item_id if body.item_id is not None else l.item_id)  # re-check after the edit; never keep a stale CONFIRMED
    if o.status == "CONFIRMED":
        o.status = "NEEDS_REVIEW"
    audit(db, user, "offer_line_edit", "offer_line", lid)
    db.commit()
    return line_out(l)


@router.delete("/offer-lines/{lid}", status_code=204)
def delete_line(lid: int, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    l = db.get(OfferLine, lid)
    if not l:
        raise HTTPException(404)
    o, _ = _offer_for_edit(db, user, l.offer_id)
    db.delete(l)
    if o.status == "CONFIRMED":
        o.status = "NEEDS_REVIEW"
    db.commit()


@router.post("/offer-lines/{lid}/match")
def set_match(lid: int, body: MatchIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    """Human decision on a suggested match. Lines with technical flags need ANALOG_APPROVED (separate, explicit)."""
    l = db.get(OfferLine, lid)
    if not l:
        raise HTTPException(404)
    o, p = _offer_for_edit(db, user, l.offer_id)
    if body.status == "UNMATCHED":
        l.item_id, l.match_status, l.tech_flags = None, "UNMATCHED", []
    else:
        if body.item_id is None:
            raise HTTPException(422, "item_id required")
        apply_match(p, l, body.item_id)
        if l.tech_flags and body.status == "CONFIRMED":
            raise HTTPException(422, {"message": "Technical differences found; approve explicitly as an analog (ANALOG_APPROVED)", "flags": l.tech_flags})
        if body.status == "ANALOG_APPROVED" and not l.tech_flags:
            body.status = "CONFIRMED"
        l.match_status = body.status
    if o.status == "CONFIRMED":
        o.status = "NEEDS_REVIEW"
    audit(db, user, "match_set", "offer_line", lid, status=l.match_status, item_id=l.item_id)
    db.commit()
    return line_out(l)


@router.post("/offers/{oid}/confirm")
def confirm_offer(oid: int, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    o, p = _offer_for_edit(db, user, oid)
    if o.prices_include_vat is None:
        raise HTTPException(422, "State whether the offer prices include VAT before confirming")
    if o.prices_include_vat is False and o.vat_rate is None:
        raise HTTPException(422, "VAT rate is required for prices without VAT")
    o.status = "CONFIRMED"
    audit(db, user, "offer_confirm", "offer", oid)
    db.commit()
    return offer_out(o)
