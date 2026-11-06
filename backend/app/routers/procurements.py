from datetime import date, datetime
from decimal import Decimal

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import EDITABLE, audit, get_editable, get_visible, has_perm, require, visible_filter
from ..models import ApprovalEvent, Item, Offer, Procurement, Status, User
from ..services import comparison as cmp
from ..services.excel import build_workbook

router = APIRouter(prefix="/api/procurements", tags=["procurements"])


class ProcurementIn(BaseModel):
    purpose: str | None = None
    justification: str | None = None
    department: str | None = None
    request_no: str | None = None
    project: str | None = None
    need_by: date | None = None
    currency: str = Field(default="UZS", min_length=3, max_length=3)
    comment: str | None = None


class ItemIn(BaseModel):
    name: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    code: str | None = None
    specs: str | None = None
    manufacturer: str | None = None
    analogs_allowed: bool = False
    requirements: str | None = None


class RateIn(BaseModel):
    rate: Decimal = Field(gt=0)
    rate_date: date = Field(alias="date")
    source: str = Field(min_length=1)


class SelectionIn(BaseModel):
    mode: str = Field(pattern="^(single|per_item)$")
    supplier_id: int | None = None
    items: dict[int, int] = {}
    reason: str = Field(min_length=10)


class TransitionIn(BaseModel):
    to: Status
    comment: str | None = None
    confirm: bool = False  # important operations must be explicitly confirmed


TRANSITIONS = {
    Status.DRAFT: {Status.PREPARED: "procurement.edit"},
    Status.RETURNED: {Status.PREPARED: "procurement.edit"},
    Status.PREPARED: {Status.IN_REVIEW: "procurement.edit", Status.DRAFT: "procurement.edit"},
    Status.IN_REVIEW: {Status.IN_APPROVAL: "review", Status.RETURNED: "review"},
    Status.IN_APPROVAL: {Status.APPROVED: "approve", Status.RETURNED: "approve", Status.REJECTED: "approve"},
}


def item_out(i: Item) -> dict:
    return {"id": i.id, "position": i.position, "name": i.name, "code": i.code, "specs": i.specs, "unit": i.unit, "quantity": format(i.quantity.normalize(), "f"),
            "manufacturer": i.manufacturer, "analogs_allowed": i.analogs_allowed, "requirements": i.requirements}


def proc_out(p: Procurement, full: bool = False) -> dict:
    d = {"id": p.id, "number": p.number, "purpose": p.purpose, "justification": p.justification, "initiator_id": p.initiator_id, "department": p.department,
         "request_no": p.request_no, "project": p.project, "need_by": p.need_by, "currency": p.currency, "comment": p.comment, "status": p.status,
         "version": p.version, "rates": p.rates, "selection": p.selection, "created_at": p.created_at, "locked": p.status not in EDITABLE}
    if full:
        d["items"] = [item_out(i) for i in p.items]
    return d


@router.post("", status_code=201)
def create(body: ProcurementIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.create"))):
    year = datetime.now().year
    n = (db.scalar(select(func.count()).select_from(Procurement).where(Procurement.number.like(f"СЛ-{year}-%"))) or 0) + 1
    p = Procurement(number=f"СЛ-{year}-{n:04d}", initiator_id=user.id, **{**body.model_dump(), "department": body.department or user.department})
    db.add(p)
    db.flush()
    audit(db, user, "procurement_create", "procurement", p.id)
    db.commit()
    return proc_out(p, True)


@router.get("")
def list_(status: str | None = None, q: str | None = None, department: str | None = None, date_from: date | None = None, date_to: date | None = None,
          limit: int = 100, offset: int = 0, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    stmt = select(Procurement).where(visible_filter(user)).order_by(Procurement.id.desc())
    if status:
        stmt = stmt.where(Procurement.status == status)
    if department:
        stmt = stmt.where(Procurement.department == department)
    if q:
        stmt = stmt.where(Procurement.number.ilike(f"%{q}%") | Procurement.purpose.ilike(f"%{q}%"))
    if date_from:
        stmt = stmt.where(Procurement.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Procurement.created_at <= datetime.combine(date_to, datetime.max.time()))
    return [proc_out(p) for p in db.scalars(stmt.limit(min(limit, 500)).offset(offset))]


@router.get("/{pid}")
def get(pid: int, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    return proc_out(get_visible(db, user, pid), True)


@router.patch("/{pid}")
def update(pid: int, body: ProcurementIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    p = get_editable(db, user, pid)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    audit(db, user, "procurement_update", "procurement", p.id)
    db.commit()
    return proc_out(p, True)


@router.delete("/{pid}", status_code=204)
def delete(pid: int, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    p = get_editable(db, user, pid)
    if p.status != Status.DRAFT.value:
        raise HTTPException(409, "Only drafts can be deleted")
    audit(db, user, "procurement_delete", "procurement", p.id, number=p.number)
    db.delete(p)
    db.commit()


# ---- items ----
@router.post("/{pid}/items", status_code=201)
def add_item(pid: int, body: ItemIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    p = get_editable(db, user, pid)
    it = Item(procurement_id=p.id, position=len(p.items) + 1, **body.model_dump())
    db.add(it)
    audit(db, user, "item_add", "procurement", p.id, name=body.name)
    db.commit()
    return item_out(it)


@router.put("/{pid}/items/{iid}")
def edit_item(pid: int, iid: int, body: ItemIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    get_editable(db, user, pid)
    it = db.get(Item, iid)
    if not it or it.procurement_id != pid:
        raise HTTPException(404)
    for k, v in body.model_dump().items():
        setattr(it, k, v)
    audit(db, user, "item_edit", "item", iid)
    db.commit()
    return item_out(it)


@router.delete("/{pid}/items/{iid}", status_code=204)
def del_item(pid: int, iid: int, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    get_editable(db, user, pid)
    it = db.get(Item, iid)
    if not it or it.procurement_id != pid:
        raise HTTPException(404)
    from ..models import OfferLine

    for ln in db.scalars(select(OfferLine).where(OfferLine.item_id == iid)):
        ln.item_id, ln.match_status = None, "UNMATCHED"  # keep the supplier's line, drop the link
    db.delete(it)
    audit(db, user, "item_delete", "item", iid)
    db.commit()


@router.post("/{pid}/rates/refresh")
def refresh_rates(pid: int, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    """One button: official CBU rates for every foreign currency used in this procurement (or USD/EUR if none yet)."""
    from ..services import cbu

    p = get_editable(db, user, pid)
    wanted = sorted({o.currency for o in p.offers} | set(p.rates)) or ["USD", "EUR"]
    wanted = [c for c in wanted if c != p.currency] or ["USD", "EUR"]
    try:
        table = cbu.fetch_cbu()
    except cbu.RatesUnavailable:
        raise HTTPException(502, "Не удалось получить курс с сайта Центрального банка. Проверьте интернет на сервере или впишите курс вручную")
    new, missing = cbu.rates_for(p.currency, wanted, table)
    if new:
        p.rates = {**p.rates, **new}
        audit(db, user, "rates_refresh", "procurement", p.id, currencies=sorted(new), source="CBU")
        db.commit()
    return {"rates": p.rates, "updated": sorted(new), "missing": missing}


@router.put("/{pid}/rates/{currency}")
def set_rate(pid: int, currency: str, body: RateIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    p = get_editable(db, user, pid)
    p.rates = {**p.rates, currency.upper(): {"rate": str(body.rate), "date": body.rate_date.isoformat(), "source": body.source}}
    audit(db, user, "rate_set", "procurement", p.id, currency=currency, rate=str(body.rate), source=body.source)
    db.commit()
    return p.rates


# ---- comparison ----
def load_full(db: Session, p: Procurement) -> Procurement:
    return db.scalar(select(Procurement).where(Procurement.id == p.id).options(selectinload(Procurement.items), selectinload(Procurement.offers).selectinload(Offer.lines), selectinload(Procurement.offers).selectinload(Offer.supplier)))


def run_comparison(p: Procurement, delivery_rule: str = "none") -> dict:
    items = [cmp.ItemIn(i.id, i.name, i.unit, i.quantity) for i in p.items]
    offers = [
        cmp.OfferIn(o.id, o.supplier_id, o.supplier.name, o.currency, o.prices_include_vat, o.vat_rate, o.discount_pct, o.delivery_cost, o.delivery_days,
                    [cmp.LineIn(l.item_id, l.unit_price, l.match_status, l.quantity, l.unit) for l in o.lines], o.status)
        for o in p.offers
    ]
    need_days = (p.need_by - date.today()).days if p.need_by else None
    return cmp.compare(items, offers, p.currency, p.rates, delivery_rule, need_days)


@router.get("/{pid}/comparison")
def comparison(pid: int, delivery_rule: str = "none", db: Session = Depends(get_db), user: User = Depends(require("view"))):
    p = load_full(db, get_visible(db, user, pid))
    res = run_comparison(p, delivery_rule)
    out = cmp.serialise(res)
    out["warnings"] = []
    if len(p.offers) < 3:
        out["warnings"].append("fewer_than_3_offers")
    if res["cheapest_complete_offer_id"] is None and p.offers:
        out["warnings"].append("no_complete_comparable_offer")
    return out


@router.put("/{pid}/selection")
def select_supplier(pid: int, body: SelectionIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    p = load_full(db, get_editable(db, user, pid))
    res = run_comparison(p)
    ok_suppliers = {o["supplier_id"] for o in res["offers"]}
    if body.mode == "single":
        if body.supplier_id not in ok_suppliers:
            raise HTTPException(422, "Supplier has no offer in this procurement")
        o = next(o for o in res["offers"] if o["supplier_id"] == body.supplier_id)
        if not o["complete"]:
            raise HTTPException(422, "Selected offer is incomplete; use per-item mode or complete the offer")
        sel = {"mode": "single", "supplier_id": body.supplier_id, "items": {}}
    else:
        item_ids = {i.id for i in p.items}
        if set(body.items) != item_ids:
            raise HTTPException(422, "per_item mode requires a supplier for every item")
        for iid, sid in body.items.items():
            o = next((o for o in res["offers"] if o["supplier_id"] == sid), None)
            if not o or o["cells"][iid]["status"] != "ok":
                raise HTTPException(422, f"Supplier {sid} has no comparable price for item {iid}")
        sel = {"mode": "per_item", "supplier_id": None, "items": {str(k): v for k, v in body.items.items()}}
    p.selection = {**sel, "reason": body.reason, "selected_by": user.id, "selected_at": datetime.now().isoformat()}
    audit(db, user, "selection_set", "procurement", p.id, selection=p.selection)
    db.commit()
    return p.selection


@router.post("/{pid}/transition")
def transition(pid: int, body: TransitionIn, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    p = load_full(db, get_visible(db, user, pid))
    cur = Status(p.status)
    perm = TRANSITIONS.get(cur, {}).get(body.to)
    if not perm:
        raise HTTPException(409, f"Transition {cur.value} -> {body.to.value} is not allowed")
    if not has_perm(user, perm):
        raise HTTPException(403, f"Missing permission: {perm}")
    if body.to in (Status.APPROVED, Status.REJECTED) and not body.confirm:
        raise HTTPException(422, "This operation must be confirmed (confirm=true)")
    if body.to in (Status.RETURNED, Status.REJECTED) and not body.comment:
        raise HTTPException(422, "A comment is required")
    if body.to == Status.PREPARED and not p.items:
        raise HTTPException(422, "Add at least one item")
    snapshot = None
    if body.to == Status.IN_REVIEW and not p.selection:
        raise HTTPException(422, "Record the supplier selection and its justification first")
    if body.to == Status.APPROVED:
        if user.id == p.initiator_id and user.role != "SUPER_ADMIN":
            raise HTTPException(403, "Initiator cannot approve their own comparison")
        res = run_comparison(p)
        pending = [l.id for o in p.offers for l in o.lines if l.match_status in ("SUGGESTED", "TECH_REVIEW", "UNMATCHED") and l.item_id]
        if pending:
            raise HTTPException(422, f"{len(pending)} offer lines still await match confirmation / technical review")
        snapshot = {"comparison": cmp.serialise(res), "selection": p.selection, "rates": p.rates}
    audit_from = p.status
    p.status = body.to.value
    db.add(ApprovalEvent(procurement_id=p.id, from_status=audit_from, to_status=p.status, user_id=user.id, comment=body.comment, snapshot=snapshot))
    audit(db, user, "status_change", "procurement", p.id, frm=audit_from, to=p.status)
    db.commit()
    return proc_out(p)


@router.post("/{pid}/new-version")
def new_version(pid: int, confirm: bool = False, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    p = get_visible(db, user, pid)
    if p.status not in (Status.APPROVED.value, Status.REJECTED.value):
        raise HTTPException(409, "Only approved/rejected documents need a new version")
    if not confirm:
        raise HTTPException(422, "Confirm creation of a new version (confirm=true)")
    db.add(ApprovalEvent(procurement_id=p.id, from_status=p.status, to_status=Status.DRAFT.value, user_id=user.id, comment=f"new version {p.version + 1}"))
    p.status, p.version = Status.DRAFT.value, p.version + 1
    audit(db, user, "new_version", "procurement", p.id, version=p.version)
    db.commit()
    return proc_out(p)


@router.get("/{pid}/history")
def history(pid: int, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    p = get_visible(db, user, pid)
    return [{"at": e.at, "from": e.from_status, "to": e.to_status, "user_id": e.user_id, "comment": e.comment} for e in db.scalars(select(ApprovalEvent).where(ApprovalEvent.procurement_id == p.id).order_by(ApprovalEvent.id))]


@router.get("/{pid}/export.xlsx")
def export(pid: int, delivery_rule: str = "none", db: Session = Depends(get_db), user: User = Depends(require("export"))):
    p = load_full(db, get_visible(db, user, pid))
    res = run_comparison(p, delivery_rule)
    initiator = db.get(User, p.initiator_id)
    hist = [{"at": e.at, "from": e.from_status, "to": e.to_status, "user": (db.get(User, e.user_id).name if e.user_id else ""), "comment": e.comment}
            for e in db.scalars(select(ApprovalEvent).where(ApprovalEvent.procurement_id == p.id).order_by(ApprovalEvent.id))]
    data = {
        "procurement": {"number": p.number, "created": p.created_at, "initiator": initiator.name if initiator else "", "department": p.department, "request_no": p.request_no,
                        "purpose": p.purpose, "need_by": p.need_by, "rates": p.rates, "selection": p.selection},
        "items": [item_out(i) | {"quantity": i.quantity} for i in p.items],
        "comparison": res,
        "offers": [{"id": o.id, "supplier": o.supplier.name, "number": o.number, "date": o.offer_date, "valid_until": o.valid_until, "currency": o.currency,
                    "prices_include_vat": o.prices_include_vat, "vat_rate": o.vat_rate, "discount_pct": o.discount_pct, "delivery_cost": o.delivery_cost,
                    "delivery_days": o.delivery_days, "payment_terms": o.payment_terms, "warranty": o.warranty, "status": o.status, "document_ids": o.document_ids,
                    "lines": [{"item_id": l.item_id, "unit_price": l.unit_price} for l in o.lines]} for o in p.offers],
        "history": hist,
    }
    audit(db, user, "export_xlsx", "procurement", p.id)
    db.commit()
    return Response(build_workbook(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(p.number)}.xlsx"})
