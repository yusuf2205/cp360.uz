import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, require
from ..models import Offer, Supplier, User

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])
LEGAL_FORMS = r"\b(ооо|ип|ао|зао|оао|мчж|xk|qk|ooo|llc|ltd|inc|co|корп|компания)\b"


def norm_name(name: str) -> str:
    s = re.sub(LEGAL_FORMS, " ", name.lower().replace("ё", "е"), flags=re.I)
    return re.sub(r"[^\w]+", " ", s).strip()


class SupplierIn(BaseModel):
    name: str
    inn: str | None = None
    contacts: dict = {}
    address: str | None = None
    bank_details: str | None = None
    active: bool = True
    comment: str | None = None


def out(s: Supplier) -> dict:
    return {"id": s.id, "name": s.name, "inn": s.inn, "contacts": s.contacts, "address": s.address, "bank_details": s.bank_details, "active": s.active, "comment": s.comment}


def find_duplicates(db: Session, name: str, inn: str | None, exclude_id: int | None = None) -> list[Supplier]:
    conds = [Supplier.name_norm == norm_name(name)]
    if inn:
        conds.append(Supplier.inn == inn)
    q = select(Supplier).where(or_(*conds))
    if exclude_id:
        q = q.where(Supplier.id != exclude_id)
    return list(db.scalars(q))


@router.get("")
def list_suppliers(q: str | None = None, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    stmt = select(Supplier).order_by(Supplier.name)
    if q:
        stmt = stmt.where(or_(Supplier.name.ilike(f"%{q}%"), Supplier.inn == q))
    return [out(s) for s in db.scalars(stmt.limit(500))]


@router.post("", status_code=201)
def create(body: SupplierIn, force: bool = False, db: Session = Depends(get_db), user: User = Depends(require("supplier.manage"))):
    dups = find_duplicates(db, body.name, body.inn)
    if dups and not force:
        raise HTTPException(409, {"message": "Possible duplicate supplier", "duplicates": [out(d) for d in dups]})
    s = Supplier(name=body.name.strip(), name_norm=norm_name(body.name), inn=body.inn, contacts=body.contacts, address=body.address, bank_details=body.bank_details, active=body.active, comment=body.comment)
    db.add(s)
    db.flush()
    audit(db, user, "supplier_create", "supplier", s.id)
    db.commit()
    return out(s)


@router.patch("/{sid}")
def update(sid: int, body: SupplierIn, db: Session = Depends(get_db), user: User = Depends(require("supplier.manage"))):
    s = db.get(Supplier, sid)
    if not s:
        raise HTTPException(404)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    s.name_norm = norm_name(s.name)
    audit(db, user, "supplier_update", "supplier", s.id)
    db.commit()
    return out(s)


@router.get("/{sid}/history")
def history(sid: int, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    from ..deps import visible_filter
    from ..models import Procurement

    rows = db.execute(
        select(Offer, Procurement).join(Procurement, Procurement.id == Offer.procurement_id).where(Offer.supplier_id == sid, visible_filter(user)).order_by(Offer.id.desc())
    ).all()
    return [{"offer_id": o.id, "procurement_id": p.id, "number": p.number, "offer_date": o.offer_date, "status": o.status, "currency": o.currency} for o, p in rows]
