from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require, visible_filter
from ..models import ApprovalEvent, AuditLog, Offer, Procurement, Status, User

router = APIRouter(prefix="/api", tags=["dashboard"])
ACTIVE = [Status.PREPARED.value, Status.IN_REVIEW.value, Status.IN_APPROVAL.value, Status.RETURNED.value]


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(require("view"))):
    vis = visible_filter(user)
    by_status = dict(db.execute(select(Procurement.status, func.count()).where(vis).group_by(Procurement.status)).all())
    total = sum(by_status.values())
    offer_counts = {pid: n for pid, n in db.execute(select(Offer.procurement_id, func.count()).group_by(Offer.procurement_id)).all()}
    active = list(db.execute(select(Procurement.id).where(vis, Procurement.status.in_(ACTIVE) | (Procurement.status == Status.DRAFT.value))).scalars())
    few_offers = [pid for pid in active if offer_counts.get(pid, 0) < 3]
    # amounts: only from frozen approval snapshots, per currency (no cross-currency summing)
    amounts: dict[str, Decimal] = {}
    for p in db.scalars(select(Procurement).where(vis, Procurement.status == Status.APPROVED.value)):
        ev = db.scalar(select(ApprovalEvent).where(ApprovalEvent.procurement_id == p.id, ApprovalEvent.to_status == "APPROVED").order_by(ApprovalEvent.id.desc()))
        snap = ev.snapshot if ev else None
        if not snap:
            continue
        c, sel = snap["comparison"], snap["selection"]
        total_sel = Decimal(0)
        if sel.get("mode") == "single":
            o = next((x for x in c["offers"] if x["supplier_id"] == sel["supplier_id"]), None)
            total_sel = Decimal(o["total"]) if o else Decimal(0)
        else:
            for iid, sid in (sel.get("items") or {}).items():
                o = next((x for x in c["offers"] if x["supplier_id"] == sid), None)
                if o and o["cells"][str(iid)].get("sum"):
                    total_sel += Decimal(o["cells"][str(iid)]["sum"])
        amounts[p.currency] = amounts.get(p.currency, Decimal(0)) + total_sel
    recent = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(15)) if user.role in ("SUPER_ADMIN", "ADMIN") else []
    return {
        "total": total,
        "active": sum(by_status.get(s, 0) for s in ACTIVE),
        "draft": by_status.get("DRAFT", 0),
        "in_review": by_status.get("IN_REVIEW", 0),
        "in_approval": by_status.get("IN_APPROVAL", 0),
        "approved": by_status.get("APPROVED", 0),
        "rejected": by_status.get("REJECTED", 0),
        "returned": by_status.get("RETURNED", 0),
        "insufficient_offers": len(few_offers),
        "approved_amount_by_currency": {k: str(v.quantize(Decimal("0.01"))) for k, v in amounts.items()},
        "confirmed_savings": None,  # needs an explicit savings baseline (not defined yet) - deliberately not guessed
        "recent": [{"action": a.action, "entity": a.entity, "entity_id": a.entity_id, "at": a.at} for a in recent],
    }
