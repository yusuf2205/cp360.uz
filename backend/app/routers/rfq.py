"""Supplier self-service quotes: buyer creates a link, supplier fills a public form, buyer accepts in one click.

Public surface is limited to /api/public/rfq/{token}. Everything a supplier submits is untrusted text/numbers:
it is validated, stored as a Submission and only becomes an Offer when an authorised buyer accepts it.
"""
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..services import notify
from ..deps import EDITABLE, audit, get_editable, get_visible, require
from ..models import Invitation, Item, Offer, OfferLine, Procurement, Submission, Supplier, User
from .suppliers import find_duplicates, norm_name

router = APIRouter(tags=["rfq"])
_hits: dict[str, list[float]] = {}  # in-memory throttle per token; use Redis for multi-worker setups


def throttle(key: str, limit: int, window: int = 600):
    now_ = time.time()
    hits = [t for t in _hits.get(key, []) if now_ - t < window]
    if len(hits) >= limit:
        raise HTTPException(429, "Слишком много запросов, повторите позже")
    _hits[key] = hits + [now_]


def limit_get(token: str):
    throttle("get:" + token, 200)


def limit_post(token: str):
    throttle("post:" + token, 40)  # runs before body validation, so malformed spam is counted too


# ---------------- schemas ----------------
class RfqLine(BaseModel):
    item_id: int
    unit_price: Decimal | None = Field(default=None, gt=0, lt=Decimal("1e15"))
    alt_name: str | None = Field(default=None, max_length=300)  # supplier offers a different product / analog
    note: str | None = Field(default=None, max_length=300)


class RfqSubmit(BaseModel):
    company: str = Field(min_length=2, max_length=300)
    inn: str | None = Field(default=None, max_length=20)
    contact_person: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    currency: str = Field(default="UZS", min_length=3, max_length=3)
    prices_include_vat: bool
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100)
    valid_days: int | None = Field(default=None, ge=1, le=365)
    delivery_days: int | None = Field(default=None, ge=0, le=730)
    delivery_terms: str | None = Field(default=None, max_length=200)
    delivery_cost: Decimal | None = Field(default=None, ge=0, lt=Decimal("1e15"))
    payment_terms: str | None = Field(default=None, max_length=300)
    warranty: str | None = Field(default=None, max_length=300)
    comment: str | None = Field(default=None, max_length=2000)
    lines: list[RfqLine] = Field(max_length=500)

    @field_validator("inn")
    @classmethod
    def inn_digits(cls, v):
        if v and not v.replace(" ", "").isdigit():
            raise ValueError("ИНН должен состоять из цифр")
        return v.replace(" ", "") if v else v


class InviteIn(BaseModel):
    supplier_id: int | None = None
    supplier_name: str | None = Field(default=None, max_length=300)
    valid_days: int = Field(default=7, ge=1, le=60)
    vat_rate_default: Decimal | None = Field(default=None, ge=0, le=100)
    message: str | None = Field(default=None, max_length=1000)


class AcceptIn(BaseModel):
    supplier_id: int | None = None
    force_new: bool = False  # create a new supplier even if possible duplicates exist (explicit user choice)


class RejectIn(BaseModel):
    comment: str = Field(min_length=3, max_length=500)


PICKUP = "Самовывоз"
SUPPLIER_DELIVERY = "Доставка поставщиком"


def delivery_cost_for(d: dict) -> Decimal | None:
    """Pickup => no delivery cost at all (explicit zero, never counted). Supplier delivery with an empty cost means
    "included in the price" (the form says so). Any other carrier with an empty cost stays unknown."""
    terms, cost = d.get("delivery_terms"), d.get("delivery_cost")
    if terms == PICKUP:
        return Decimal(0)
    if cost is not None:
        return Decimal(str(cost))
    return Decimal(0) if terms == SUPPLIER_DELIVERY else None


# ---------------- helpers ----------------
def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def summarise(payload: dict, items: list[Item]) -> dict:
    """Totals for the buyer's preview. Quantities come from OUR item list, never from the supplier."""
    by_id = {i.id: i for i in items}
    total = Decimal(0)
    priced = 0
    rate = Decimal(str(payload["vat_rate"])) if payload.get("vat_rate") is not None else None
    for ln in payload["lines"]:
        it = by_id.get(ln["item_id"])
        if not it or ln.get("unit_price") is None:
            continue
        price = Decimal(str(ln["unit_price"]))
        if not payload["prices_include_vat"]:
            price = price * (1 + (rate or Decimal(0)) / 100)
        total += price * it.quantity
        priced += 1
    return {"total_with_vat": format(total.quantize(Decimal("0.01")), "f"), "priced": priced, "missing": len(items) - priced,
            "has_analogs": any(l.get("alt_name") for l in payload["lines"])}


def sub_out(s: Submission, items: list[Item]) -> dict:
    return {"id": s.id, "invitation_id": s.invitation_id, "status": s.status, "revision": s.revision, "payload": s.payload, "summary": summarise(s.payload, items),
            "offer_id": s.offer_id, "decision_comment": s.decision_comment, "submitted_at": s.submitted_at}


def inv_out(i: Invitation, latest: Submission | None, items: list[Item]) -> dict:
    expired = _utc(i.expires_at) < datetime.now(timezone.utc)
    return {"id": i.id, "token": i.token, "supplier_id": i.supplier_id, "supplier_hint": i.supplier_hint, "message": i.message, "expires_at": i.expires_at,
            "status": "EXPIRED" if (i.status == "ACTIVE" and expired) else i.status, "created_at": i.created_at,
            "submission": sub_out(latest, items) if latest else None}


# ---------------- buyer side (authenticated) ----------------
@router.post("/api/procurements/{pid}/invitations", status_code=201)
def create_invitation(pid: int, body: InviteIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    p = get_editable(db, user, pid)
    if not p.items:
        raise HTTPException(422, "Добавьте товары в закупку, прежде чем отправлять ссылку поставщику")
    hint = body.supplier_name
    if body.supplier_id:
        s = db.get(Supplier, body.supplier_id)
        if not s:
            raise HTTPException(422, "Unknown supplier")
        hint = hint or s.name
    inv = Invitation(procurement_id=p.id, token=secrets.token_urlsafe(24), supplier_id=body.supplier_id, supplier_hint=hint, message=body.message,
                     vat_rate_default=body.vat_rate_default, expires_at=datetime.now(timezone.utc) + timedelta(days=body.valid_days), created_by=user.id)
    db.add(inv)
    db.flush()
    audit(db, user, "invitation_create", "invitation", inv.id, procurement_id=p.id)
    db.commit()
    return inv_out(inv, None, p.items)


@router.get("/api/procurements/{pid}/invitations")
def list_invitations(pid: int, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    p = get_visible(db, user, pid)
    out = []
    for inv in db.scalars(select(Invitation).where(Invitation.procurement_id == p.id).order_by(Invitation.id.desc())):
        latest = db.scalar(select(Submission).where(Submission.invitation_id == inv.id).order_by(Submission.id.desc()))
        out.append(inv_out(inv, latest, p.items))
    return out


@router.delete("/api/invitations/{iid}", status_code=204)
def revoke_invitation(iid: int, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    inv = db.get(Invitation, iid)
    if not inv:
        raise HTTPException(404)
    get_visible(db, user, inv.procurement_id)
    inv.status = "REVOKED"
    audit(db, user, "invitation_revoke", "invitation", iid)
    db.commit()


def _load_sub(db: Session, user: User, sid: int) -> tuple[Submission, Procurement]:
    s = db.get(Submission, sid)
    if not s:
        raise HTTPException(404)
    return s, get_editable(db, user, s.procurement_id)


@router.post("/api/submissions/{sid}/accept")
def accept(sid: int, body: AcceptIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    """One click: supplier answer -> confirmed offer in the comparison. Analogs go to technical review."""
    s, p = _load_sub(db, user, sid)
    if s.status != "NEW":
        raise HTTPException(409, "Ответ уже обработан")
    inv = db.get(Invitation, s.invitation_id)
    d = s.payload
    sup_id = body.supplier_id or (inv.supplier_id if inv else None)
    if sup_id:
        sup = db.get(Supplier, sup_id)
        if not sup:
            raise HTTPException(422, "Unknown supplier")
    else:
        dups = [] if body.force_new else find_duplicates(db, d["company"], d.get("inn"))
        if dups:
            raise HTTPException(409, {"message": "Возможно, такой поставщик уже есть", "duplicates": [{"id": x.id, "name": x.name, "inn": x.inn} for x in dups]})
        sup = Supplier(name=d["company"].strip(), name_norm=norm_name(d["company"]), inn=d.get("inn"),
                       contacts={k: d.get(k) for k in ("contact_person", "phone", "email") if d.get(k)})
        db.add(sup)
        db.flush()
    if db.scalar(select(Offer).where(Offer.procurement_id == p.id, Offer.supplier_id == sup.id)):
        raise HTTPException(409, "У этого поставщика уже есть предложение в закупке. Удалите его или обновите вручную")

    notes = "; ".join(x for x in (d.get("comment"), (f"Условие доставки: {d['delivery_terms']}" + (" (стоимость включена в цену)" if d.get("delivery_terms") == SUPPLIER_DELIVERY and d.get("delivery_cost") is None else "")) if d.get("delivery_terms") else None,
                                  f"Контакт: {d.get('contact_person')} {d.get('phone') or ''} {d.get('email') or ''}".strip() if d.get("contact_person") or d.get("phone") or d.get("email") else None) if x)
    o = Offer(procurement_id=p.id, supplier_id=sup.id, offer_date=date.today(), valid_until=(date.today() + timedelta(days=d["valid_days"])) if d.get("valid_days") else None,
              currency=d["currency"], prices_include_vat=d["prices_include_vat"], vat_rate=Decimal(str(d["vat_rate"])) if d.get("vat_rate") is not None else None,
              delivery_cost=delivery_cost_for(d), delivery_days=d.get("delivery_days"),  # for pickup: days until the goods are ready
              payment_terms=d.get("payment_terms"), warranty=d.get("warranty"), notes=notes or None, status="CONFIRMED", document_ids=[])
    db.add(o)
    db.flush()
    items = {i.id: i for i in p.items}
    for ln in d["lines"]:
        it = items.get(ln["item_id"])
        if not it or ln.get("unit_price") is None:
            continue
        analog = bool(ln.get("alt_name"))
        db.add(OfferLine(offer_id=o.id, item_id=it.id, raw_name=ln["alt_name"] if analog else it.name, unit=it.unit, quantity=it.quantity, unit_price=Decimal(str(ln["unit_price"])),
                         match_status="TECH_REVIEW" if analog else "CONFIRMED", match_score=None, tech_flags=["analog_offered"] if analog else [],
                         provenance={"submission_id": s.id, "note": ln.get("note")}, original={"unit_price": str(ln["unit_price"]), "alt_name": ln.get("alt_name")}))
    if any(l.get("alt_name") and l.get("unit_price") is not None for l in d["lines"]):
        o.status = "NEEDS_REVIEW"  # an analog must be approved before the offer counts as confirmed
    s.status, s.offer_id, s.decided_by = "ACCEPTED", o.id, user.id
    audit(db, user, "submission_accept", "submission", s.id, offer_id=o.id)
    db.commit()
    return {"offer_id": o.id, "supplier_id": sup.id, "status": o.status}


@router.post("/api/submissions/{sid}/reject")
def reject(sid: int, body: RejectIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    s, _ = _load_sub(db, user, sid)
    if s.status != "NEW":
        raise HTTPException(409, "Ответ уже обработан")
    s.status, s.decided_by, s.decision_comment = "REJECTED", user.id, body.comment
    audit(db, user, "submission_reject", "submission", s.id)
    db.commit()
    return {"status": s.status}


# ---------------- public side (no login; token only) ----------------
def _active_invitation(db: Session, token: str) -> tuple[Invitation, Procurement]:
    inv = db.scalar(select(Invitation).where(Invitation.token == token))
    if not inv or inv.status != "ACTIVE":
        raise HTTPException(404, "Ссылка недействительна")
    if _utc(inv.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(410, "Срок действия ссылки истёк. Запросите новую у заказчика")
    p = db.get(Procurement, inv.procurement_id)
    if not p or p.status not in EDITABLE:
        raise HTTPException(410, "Приём предложений по этой закупке закрыт")
    return inv, p


@router.get("/api/public/rfq/{token}")
def public_get(token: str, db: Session = Depends(get_db), _: None = Depends(limit_get)):
    inv, p = _active_invitation(db, token)
    latest = db.scalar(select(Submission).where(Submission.invitation_id == inv.id).order_by(Submission.id.desc()))
    # Only what the supplier needs. No other suppliers, prices, internal comments or user data.
    return {
        "number": p.number, "purpose": p.purpose, "need_by": p.need_by, "currency": p.currency, "message": inv.message, "supplier_hint": inv.supplier_hint,
        "vat_rate_default": format(inv.vat_rate_default.normalize(), "f") if inv.vat_rate_default is not None else None, "expires_at": inv.expires_at,
        "items": [{"id": i.id, "position": n + 1, "name": i.name, "code": i.code, "specs": i.specs, "unit": i.unit, "quantity": format(i.quantity.normalize(), "f"),
                   "manufacturer": i.manufacturer, "requirements": i.requirements} for n, i in enumerate(p.items)],
        "submission": {"status": latest.status, "revision": latest.revision, "payload": latest.payload} if latest and latest.status != "REJECTED" else None,
    }


@router.post("/api/public/rfq/{token}", status_code=201)
def public_submit(token: str, body: RfqSubmit, bg: BackgroundTasks, db: Session = Depends(get_db), _: None = Depends(limit_post)):
    inv, p = _active_invitation(db, token)
    ids = [l.item_id for l in body.lines]
    if len(ids) != len(set(ids)) or not set(ids) <= {i.id for i in p.items}:
        raise HTTPException(422, "Некорректный список позиций")
    if not any(l.unit_price is not None for l in body.lines):
        raise HTTPException(422, "Укажите цену хотя бы по одной позиции")
    if not body.prices_include_vat and body.vat_rate is None:
        raise HTTPException(422, "Укажите ставку НДС, если цены указаны без НДС")
    if body.currency != p.currency and body.currency not in (p.rates or {}):
        raise HTTPException(422, f"Валюта {body.currency} не поддерживается для этой закупки (допустима {p.currency})")
    payload = body.model_dump(mode="json")
    if payload.get("delivery_terms") == PICKUP:
        payload["delivery_cost"] = None  # pickup: whatever was typed earlier is discarded, delivery is never counted
    last = db.scalar(select(Submission).where(Submission.invitation_id == inv.id).order_by(Submission.id.desc()))
    if last and last.status == "ACCEPTED":
        raise HTTPException(409, "Ваше предложение уже принято. Для изменений свяжитесь с заказчиком")
    if last and last.status == "NEW":
        last.payload, last.revision = payload, last.revision + 1  # supplier corrects own answer before the buyer decides
        s = last
    else:
        s = Submission(invitation_id=inv.id, procurement_id=p.id, payload=payload)
        db.add(s)
    db.flush()
    audit(db, None, "rfq_submit", "submission", s.id, invitation_id=inv.id, revision=s.revision)
    db.commit()
    if notify.configured():
        link = f"{settings.public_base_url.rstrip('/')}/compare" if settings.public_base_url else None
        bg.add_task(notify.supplier_answered, p.number, payload.get("company") or "—", s.revision, link)
    return {"ok": True, "revision": s.revision}
