from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import audit, get_editable, get_visible, require
from ..models import Document, FieldCorrection, Offer, OfferLine, Supplier, User
from ..services import matching, pipeline
from ..services.extraction.parsers import UnsupportedFile
from .offers import apply_match, offer_out
from .suppliers import find_duplicates, norm_name

router = APIRouter(prefix="/api/imports", tags=["smart-import"])


def doc_out(d: Document, detail: bool = False) -> dict:
    o = {"id": d.id, "procurement_id": d.procurement_id, "filename": d.filename, "kind": d.kind, "status": d.status, "error": d.error, "created_at": d.created_at}
    if detail:
        o["extraction"] = d.extraction
        o["text"] = d.extracted_text
    return o


@router.post("", status_code=202)
async def upload(background: BackgroundTasks, files: list[UploadFile] = File(default=[]), text: str | None = Form(default=None), procurement_id: int | None = Form(default=None),
                 db: Session = Depends(get_db), user: User = Depends(require("import.upload"))):
    if procurement_id is not None:
        get_editable(db, user, procurement_id)
    payload: list[tuple[str, bytes]] = []
    for f in files:
        data = await f.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"{f.filename}: larger than {settings.max_upload_mb} MB")
        payload.append((f.filename or "file", data))
    if text and text.strip():
        payload.append(("pasted-text.txt", text.encode("utf-8")))
    if not payload:
        raise HTTPException(422, "No files or text provided")
    if len(payload) > settings.max_files_per_upload:
        raise HTTPException(413, f"At most {settings.max_files_per_upload} files per upload")
    results = []
    for name, data in payload:
        try:
            doc, created = pipeline.register_upload(db, data, name, procurement_id, user.id)
        except UnsupportedFile as e:
            results.append({"filename": name, "error": str(e)})
            continue
        except OSError:
            db.rollback()
            raise HTTPException(503, "Не удалось сохранить файл на сервере (хранилище недоступно). Сообщите администратору.")
        if created or doc.status in ("ERROR", "QUEUED"):
            doc.status = "QUEUED"
            background.add_task(pipeline.process_document, doc.id)
        results.append({**doc_out(doc), "duplicate_upload": not created})
        audit(db, user, "document_upload", "document", doc.id, filename=name, duplicate=not created)
    db.commit()
    return results


@router.get("")
def list_docs(procurement_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    stmt = select(Document).order_by(Document.id.desc()).limit(200)
    if procurement_id is not None:
        get_visible(db, user, procurement_id)
        stmt = stmt.where(Document.procurement_id == procurement_id)
    else:
        stmt = stmt.where(Document.uploaded_by == user.id)
    return [doc_out(d) for d in db.scalars(stmt)]


def _load_doc(db: Session, user: User, did: int) -> Document:
    d = db.get(Document, did)
    if not d:
        raise HTTPException(404)
    if d.procurement_id is not None:
        get_visible(db, user, d.procurement_id)
    elif d.uploaded_by != user.id:
        raise HTTPException(404)
    return d


@router.get("/{did}")
def get_doc(did: int, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    d = _load_doc(db, user, did)
    out = doc_out(d, True)
    if d.extraction and d.procurement_id:
        p = get_visible(db, user, d.procurement_id)
        cands = [{"id": i.id, "name": i.name, "unit": i.unit, "specs": i.specs} for i in p.items]
        out["line_suggestions"] = [matching.suggest(cands, ln["name"], ln.get("unit")) for ln in d.extraction["lines"]]
        s = d.extraction.get("supplier") or {}
        if s.get("name"):
            out["supplier_candidates"] = [{"id": x.id, "name": x.name, "inn": x.inn} for x in find_duplicates(db, s["name"], s.get("inn"))]
        else:
            out["supplier_candidates"] = []
        dup_names = {}
        for idx, ln in enumerate(d.extraction["lines"]):
            dup_names.setdefault(matching.normalise(ln["name"]), []).append(idx)
        out["possible_duplicate_lines"] = [v for v in dup_names.values() if len(v) > 1]
    return out


@router.get("/{did}/original")
def original(did: int, db: Session = Depends(get_db), user: User = Depends(require("view"))):
    d = _load_doc(db, user, did)
    audit(db, user, "document_download", "document", d.id)
    db.commit()
    return FileResponse(d.path, filename=d.filename, headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


@router.post("/{did}/retry", status_code=202)
def retry(did: int, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(require("import.upload"))):
    d = _load_doc(db, user, did)
    if d.status not in ("ERROR", "NEEDS_REVIEW"):
        raise HTTPException(409, "Only failed or unreviewed documents can be re-processed")
    d.status = "QUEUED"
    db.commit()
    background.add_task(pipeline.process_document, d.id)
    return doc_out(d)


class ApplyLine(BaseModel):
    name: str = Field(min_length=1)
    unit: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = Field(default=None, gt=0)
    item_id: int | None = None
    confirm_match: bool = False  # user clicked "match is correct" for item_id
    src_index: int | None = None  # index in the extraction, to keep original + provenance


class ApplyIn(BaseModel):
    supplier_id: int | None = None
    new_supplier: dict | None = None  # {name, inn?, contacts?}
    offer_id: int | None = None  # merge into an existing offer (same supplier only)
    allow_overwrite: bool = False  # required to change prices of an already CONFIRMED offer
    offer: dict = {}
    lines: list[ApplyLine]


def _dec(v):
    try:
        return Decimal(str(v)) if v not in (None, "") else None
    except InvalidOperation:
        raise HTTPException(422, f"Invalid number: {v}")


@router.post("/{did}/apply")
def apply(did: int, body: ApplyIn, db: Session = Depends(get_db), user: User = Depends(require("procurement.edit"))):
    d = _load_doc(db, user, did)
    if d.procurement_id is None:
        raise HTTPException(422, "Attach the document to a procurement first")
    p = get_editable(db, user, d.procurement_id)
    ex = d.extraction or {}
    # supplier: explicit choice only; never silently merged or created
    if body.supplier_id:
        sup = db.get(Supplier, body.supplier_id)
        if not sup:
            raise HTTPException(422, "Unknown supplier")
    elif body.new_supplier and body.new_supplier.get("name"):
        dups = find_duplicates(db, body.new_supplier["name"], body.new_supplier.get("inn"))
        if dups:
            raise HTTPException(409, {"message": "Possible duplicate supplier; choose an existing one", "duplicates": [{"id": x.id, "name": x.name, "inn": x.inn} for x in dups]})
        sup = Supplier(name=body.new_supplier["name"].strip(), name_norm=norm_name(body.new_supplier["name"]), inn=body.new_supplier.get("inn"), contacts=body.new_supplier.get("contacts") or {})
        db.add(sup)
        db.flush()
    else:
        raise HTTPException(422, "Choose a supplier (supplier_id) or provide new_supplier")

    existing = db.get(Offer, body.offer_id) if body.offer_id else db.scalar(select(Offer).where(Offer.procurement_id == p.id, Offer.supplier_id == sup.id))
    if body.offer_id and (not existing or existing.procurement_id != p.id):
        raise HTTPException(404, "Offer not found")
    if existing and existing.supplier_id != sup.id:
        raise HTTPException(422, "Documents of different suppliers are never merged into one offer")
    if existing and existing.status == "CONFIRMED" and not body.allow_overwrite:
        raise HTTPException(409, "Offer is confirmed; set allow_overwrite=true to change it")
    fields = {k: v for k, v in body.offer.items() if k in ("number", "offer_date", "valid_until", "currency", "prices_include_vat", "vat_rate", "discount_pct", "delivery_cost", "delivery_days", "payment_terms", "warranty", "notes")}
    for k in ("vat_rate", "discount_pct", "delivery_cost"):
        if k in fields:
            fields[k] = _dec(fields[k])
    for k in ("offer_date", "valid_until"):
        if isinstance(fields.get(k), str):
            from datetime import date

            fields[k] = date.fromisoformat(fields[k])
    if existing:
        o = existing
        for k, v in fields.items():
            if v is not None:
                setattr(o, k, v)
    else:
        o = Offer(procurement_id=p.id, supplier_id=sup.id, **fields)
        db.add(o)
        db.flush()
    o.status = "NEEDS_REVIEW"
    o.document_ids = sorted(set(o.document_ids or []) | {d.id})

    existing_lines = {matching.normalise(l.raw_name): l for l in o.lines}
    for ln in body.lines:
        src = (ex.get("lines") or [])[ln.src_index] if ln.src_index is not None and ln.src_index < len(ex.get("lines") or []) else None
        key = matching.normalise(ln.name)
        line = existing_lines.get(key)
        if line is not None and line.unit_price is not None and ln.unit_price is not None and line.unit_price != ln.unit_price and not body.allow_overwrite:
            raise HTTPException(409, f"'{ln.name}': a different price already exists; set allow_overwrite=true to replace it")
        if line is None:
            line = OfferLine(offer_id=o.id, raw_name=ln.name)
            db.add(line)
        line.raw_name, line.unit, line.quantity, line.unit_price = ln.name, ln.unit, ln.quantity, ln.unit_price
        if src:
            line.confidence = src.get("confidence")
            line.provenance = {"document_id": d.id, "source": src.get("source")}
            line.original = {k: src.get(k) for k in ("name", "unit", "quantity", "unit_price")}
            db.flush()
            for field, ours, theirs in (("name", ln.name, src.get("name")), ("unit", ln.unit, src.get("unit")), ("quantity", ln.quantity, src.get("quantity")), ("unit_price", ln.unit_price, src.get("unit_price"))):
                a, b = (None if ours is None else str(ours)), (None if theirs is None else str(theirs))
                if field in ("quantity", "unit_price") and a is not None and b is not None:
                    a, b = str(Decimal(a).normalize()), str(Decimal(b).normalize())
                if a != b:
                    db.add(FieldCorrection(entity="offer_line", entity_id=line.id, field=field, old_value=b, new_value=a, user_id=user.id))
        apply_match(p, line, ln.item_id, ln.confirm_match)
    d.status = "PROCESSED"
    audit(db, user, "import_apply", "offer", o.id, document_id=d.id)
    db.commit()
    db.refresh(o)
    return offer_out(o)
