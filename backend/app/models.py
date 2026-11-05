import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now():
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    PROCUREMENT_MANAGER = "PROCUREMENT_MANAGER"
    REVIEWER = "REVIEWER"
    APPROVER = "APPROVER"
    VIEWER = "VIEWER"


class Status(str, enum.Enum):
    DRAFT = "DRAFT"
    PREPARED = "PREPARED"
    IN_REVIEW = "IN_REVIEW"
    IN_APPROVAL = "IN_APPROVAL"
    APPROVED = "APPROVED"
    RETURNED = "RETURNED"
    REJECTED = "REJECTED"


Money = Numeric(24, 6)
Qty = Numeric(24, 6)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)  # optional: staff sign in by phone
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)  # normalised digits, e.g. 998901234567
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))  # only for the break-glass admin password login
    role: Mapped[str] = mapped_column(String(32), default=Role.VIEWER.value)
    department: Mapped[str | None] = mapped_column(String(255))
    extra_permissions: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    name_norm: Mapped[str] = mapped_column(String(500), index=True)
    inn: Mapped[str | None] = mapped_column(String(20), index=True)
    contacts: Mapped[dict] = mapped_column(JSON, default=dict)
    address: Mapped[str | None] = mapped_column(Text)
    bank_details: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Procurement(Base):
    __tablename__ = "procurements"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    justification: Mapped[str | None] = mapped_column(Text)
    initiator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    department: Mapped[str | None] = mapped_column(String(255), index=True)
    request_no: Mapped[str | None] = mapped_column(String(64))
    project: Mapped[str | None] = mapped_column(String(255))
    need_by: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="UZS")
    comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=Status.DRAFT.value, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # {"USD": {"rate": "12650.50", "date": "2026-11-01", "source": "CBU"}}: rate = units of procurement currency per 1 unit
    rates: Mapped[dict] = mapped_column(JSON, default=dict)
    # {"mode": "single"|"per_item", "supplier_id": 3, "items": {"<item_id>": supplier_id}, "reason": "...", "confirmed_by": 1}
    selection: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    items: Mapped[list["Item"]] = relationship(cascade="all, delete-orphan", order_by="Item.position")
    offers: Mapped[list["Offer"]] = relationship(cascade="all, delete-orphan")


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    procurement_id: Mapped[int] = mapped_column(ForeignKey("procurements.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(String(128))
    specs: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[Decimal] = mapped_column(Qty)
    manufacturer: Mapped[str | None] = mapped_column(String(255))
    analogs_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    requirements: Mapped[str | None] = mapped_column(Text)


class Offer(Base):
    __tablename__ = "offers"
    id: Mapped[int] = mapped_column(primary_key=True)
    procurement_id: Mapped[int] = mapped_column(ForeignKey("procurements.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    number: Mapped[str | None] = mapped_column(String(128))
    offer_date: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="UZS")
    prices_include_vat: Mapped[bool | None] = mapped_column(Boolean)  # None = unknown
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))  # percent, e.g. 12
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    delivery_cost: Mapped[Decimal | None] = mapped_column(Money)
    delivery_days: Mapped[int | None] = mapped_column(Integer)
    payment_terms: Mapped[str | None] = mapped_column(Text)
    warranty: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")  # DRAFT | NEEDS_REVIEW | CONFIRMED
    document_ids: Mapped[list] = mapped_column(JSON, default=list)
    lines: Mapped[list["OfferLine"]] = relationship(cascade="all, delete-orphan")
    supplier: Mapped[Supplier] = relationship()


class OfferLine(Base):
    __tablename__ = "offer_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    raw_name: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(32))
    quantity: Mapped[Decimal | None] = mapped_column(Qty)
    unit_price: Mapped[Decimal | None] = mapped_column(Money)  # None = unknown, never zero
    match_status: Mapped[str] = mapped_column(String(24), default="UNMATCHED")
    # UNMATCHED | SUGGESTED | CONFIRMED | TECH_REVIEW | ANALOG_APPROVED
    match_score: Mapped[float | None] = mapped_column()
    tech_flags: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column()
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)  # field -> {doc, page, snippet}
    original: Mapped[dict] = mapped_column(JSON, default=dict)  # values as extracted, before human edits


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    procurement_id: Mapped[int | None] = mapped_column(ForeignKey("procurements.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(16))  # pdf|image|xlsx|docx|text|audio
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    path: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default="UPLOADED")
    # UPLOADED QUEUED ANALYZING NEEDS_REVIEW PROCESSED ERROR
    error: Mapped[str | None] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extraction: Mapped[dict | None] = mapped_column(JSON)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("procurement_id", "sha256", name="uq_doc_proc_hash"),)


class FieldCorrection(Base):
    __tablename__ = "field_corrections"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApprovalEvent(Base):
    __tablename__ = "approval_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    procurement_id: Mapped[int] = mapped_column(ForeignKey("procurements.id"), index=True)
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict | None] = mapped_column(JSON)  # frozen comparison at approval
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Invitation(Base):
    """Public capability link a buyer sends to one supplier. The token is the only credential; revocable, expiring."""
    __tablename__ = "invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    procurement_id: Mapped[int] = mapped_column(ForeignKey("procurements.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    supplier_hint: Mapped[str | None] = mapped_column(String(300))
    message: Mapped[str | None] = mapped_column(Text)
    vat_rate_default: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")  # ACTIVE | REVOKED
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Submission(Base):
    """What a supplier typed into the public form. Never touches comparisons until a buyer accepts it."""
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    invitation_id: Mapped[int] = mapped_column(ForeignKey("invitations.id"), index=True)
    procurement_id: Mapped[int] = mapped_column(ForeignKey("procurements.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="NEW")  # NEW | ACCEPTED | REJECTED
    payload: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    offer_id: Mapped[int | None] = mapped_column(Integer)
    decided_by: Mapped[int | None] = mapped_column(Integer)
    decision_comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class UserSession(Base):
    """One signed-in device. Long-lived (sign in once); the admin can see and revoke every device."""
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    poll_secret: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")  # ACTIVE | PENDING | DENIED | REVOKED
    device: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
