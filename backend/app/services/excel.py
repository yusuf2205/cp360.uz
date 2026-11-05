"""XLSX comparative sheet. Layout follows the corporate form: fixed left columns, two-level header,
per-supplier sub-columns (price with VAT / sum with VAT), live formulas, SUM total row."""
import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.page import PageMargins

THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD = PatternFill("solid", fgColor="D9E1F2")
BEST = PatternFill("solid", fgColor="C6EFCE")
CHOSEN = PatternFill("solid", fgColor="FFEB9C")
BAD = PatternFill("solid", fgColor="F8CBAD")
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
NUM_FMT = '#,##0.00'
FIXED = 4  # №, name, unit, qty
DASH = "—"


def _cell(ws, r, c, v=None, bold=False, fill=None, align=WRAP, fmt=None, border=True, formula=False):
    cell = ws.cell(row=r, column=c, value=v)
    if isinstance(v, str) and v.startswith('=') and not formula:
        cell.data_type = 's'  # external text (supplier/item names, notes) must never become a formula
    cell.font = Font(bold=bold, name="Calibri", size=10)
    cell.alignment = align
    if border:
        cell.border = BORDER
    if fill:
        cell.fill = fill
    if fmt:
        cell.number_format = fmt
    return cell


def _fmt_date(d):
    return d.strftime("%d.%m.%Y") if d else DASH


def build_workbook(data: dict) -> bytes:
    p, items, cmp_, offers = data["procurement"], data["items"], data["comparison"], data["offers"]
    cur = cmp_["currency"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Сравнительный лист"

    n_sup = len(cmp_["offers"])
    last_col = FIXED + 2 * max(n_sup, 1)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    _cell(ws, 1, 1, f"{data.get('company', '')}  СРАВНИТЕЛЬНЫЙ ЛИСТ № {p['number']} от {_fmt_date(p['created'])}".strip(), bold=True, align=CENTER, border=False).font = Font(bold=True, size=14)
    meta = [
        ("Инициатор", p["initiator"]), ("Подразделение", p["department"] or DASH), ("Заявка №", p["request_no"] or DASH),
        ("Назначение", p["purpose"] or DASH), ("Срок потребности", _fmt_date(p["need_by"])),
        ("Валюта сравнения", f"{cur} (все цены приведены к ценам с НДС)"),
    ]
    for i, (k, v) in enumerate(meta):
        r = 2 + i // 2
        c = 1 if i % 2 == 0 else FIXED + 1
        span_end = FIXED if i % 2 == 0 else last_col
        ws.merge_cells(start_row=r, start_column=c, end_row=r, end_column=span_end)
        _cell(ws, r, c, f"{k}: {v}", border=False)

    H1, H2 = 6, 7
    for c, t in enumerate(["№", "Наименование", "Ед. изм.", "Кол-во"], 1):
        ws.merge_cells(start_row=H1, start_column=c, end_row=H2, end_column=c)
        for rr in (H1, H2):
            _cell(ws, rr, c)
        _cell(ws, H1, c, t, bold=True, fill=HEAD, align=CENTER)
    chosen_ids = set()
    sel = p.get("selection") or {}
    if sel.get("supplier_id"):
        chosen_ids.add(sel["supplier_id"])
    chosen_ids |= set((sel.get("items") or {}).values())

    price_cols, sum_cols = [], []
    for s, o in enumerate(cmp_["offers"]):
        c = FIXED + 1 + 2 * s
        price_cols.append(c)
        sum_cols.append(c + 1)
        ws.merge_cells(start_row=H1, start_column=c, end_row=H1, end_column=c + 1)
        fill = CHOSEN if o["supplier_id"] in chosen_ids else HEAD
        _cell(ws, H1, c, o["supplier_name"], bold=True, fill=fill, align=CENTER)
        _cell(ws, H1, c + 1, None, fill=fill)
        _cell(ws, H2, c, "Цена с НДС", bold=True, fill=fill, align=CENTER)
        _cell(ws, H2, c + 1, "Сумма с НДС", bold=True, fill=fill, align=CENTER)

    first = H2 + 1
    for i, it in enumerate(items):
        r = first + i
        _cell(ws, r, 1, i + 1, align=CENTER)
        _cell(ws, r, 2, it["name"] + (f"\n{it['specs']}" if it.get("specs") else ""))
        _cell(ws, r, 3, it["unit"], align=CENTER)
        _cell(ws, r, 4, it["quantity"], fmt="#,##0.###", align=Alignment(horizontal="right", vertical="top"))
        for s, o in enumerate(cmp_["offers"]):
            cell = o["cells"][it["id"]]
            pc, sc = price_cols[s], sum_cols[s]
            if cell["status"] == "ok":
                _cell(ws, r, pc, cell["unit_price"].quantize(Decimal("0.01")), fmt=NUM_FMT)
                _cell(ws, r, sc, f"=$D{r}*{L(pc)}{r}", fmt=NUM_FMT, formula=True)  # quantity x unit price
            else:
                _cell(ws, r, pc, DASH, align=CENTER)
                _cell(ws, r, sc, DASH, align=CENTER)
        ws.row_dimensions[r].height = max(30, 15 * (1 + len(it["name"]) // 45))
    last = first + len(items) - 1
    if n_sup and items:
        refs = ",".join(f"${L(c)}{first}" for c in price_cols)
        # highlight best price in every row (dynamic: reacts to manual edits)
        for r in range(first, last + 1):
            rrefs = ",".join(f"${L(c)}{r}" for c in price_cols)
            for pc in price_cols:
                ws.conditional_formatting.add(f"{L(pc)}{r}", FormulaRule(formula=[f"AND(ISNUMBER({L(pc)}{r}),{L(pc)}{r}=MIN({rrefs}))"], fill=BEST))

    tr = last + 1
    ws.merge_cells(start_row=tr, start_column=1, end_row=tr, end_column=FIXED)
    _cell(ws, tr, 1, "ИТОГО с НДС", bold=True, fill=HEAD, align=Alignment(horizontal="right"))
    for c in range(2, FIXED + 1):
        _cell(ws, tr, c, None, fill=HEAD)
    for s, o in enumerate(cmp_["offers"]):
        _cell(ws, tr, price_cols[s], None, fill=HEAD)
        sc = sum_cols[s]
        _cell(ws, tr, sc, f"=SUM({L(sc)}{first}:{L(sc)}{last})" if items else 0, bold=True, fill=HEAD, fmt=NUM_FMT, formula=True)
        if o["offer_id"] == cmp_["cheapest_complete_offer_id"]:
            ws.cell(row=tr, column=sc).fill = BEST

    extra = [
        ("Доставка", lambda o: o["delivery"].quantize(Decimal("0.01")) if o["delivery"] is not None else DASH, NUM_FMT),
        ("Срок поставки, дн.", lambda o: o["delivery_days"] if o["delivery_days"] is not None else DASH, None),
        ("Полнота предложения", lambda o: "Полное" if o["complete"] else f"Неполное: нет {len(o['missing_items'])} поз.", None),
        ("Замечания", lambda o: "; ".join(o["flags"]) or DASH, None),
    ]
    r = tr + 1
    ometa = {o["id"]: o for o in offers}
    extra.insert(1, ("Условия оплаты", lambda o: ometa[o["offer_id"]].get("payment_terms") or DASH, None))
    extra.insert(2, ("Гарантия", lambda o: ometa[o["offer_id"]].get("warranty") or DASH, None))
    for label, fn, fmt in extra:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=FIXED)
        _cell(ws, r, 1, label, bold=True, align=Alignment(horizontal="right", vertical="top"))
        for c in range(2, FIXED + 1):
            _cell(ws, r, c)
        for s, o in enumerate(cmp_["offers"]):
            ws.merge_cells(start_row=r, start_column=price_cols[s], end_row=r, end_column=sum_cols[s])
            _cell(ws, r, price_cols[s], fn(o), fmt=fmt, fill=None if o["complete"] or label != "Полнота предложения" else None)
            _cell(ws, r, sum_cols[s])
            if label == "Полнота предложения" and not o["complete"]:
                ws.cell(row=r, column=price_cols[s]).fill = BAD
        r += 1

    r += 1
    sel_text = "Выбор не зафиксирован"
    if sel.get("supplier_id") or sel.get("items"):
        names = {o["supplier_id"]: o["supplier_name"] for o in cmp_["offers"]}
        if sel.get("mode") == "per_item":
            sel_text = "По позициям: " + "; ".join(f"поз. {k} — {names.get(v, v)}" for k, v in sel["items"].items())
        else:
            sel_text = f"Выбранный поставщик: {names.get(sel['supplier_id'], sel['supplier_id'])}"
    for label, val in (("Решение", sel_text), ("Основание выбора", sel.get("reason") or DASH)):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=last_col)
        _cell(ws, r, 1, f"{label}: {val}", bold=label == "Решение", border=False)
        ws.row_dimensions[r].height = 32
        r += 1
    r += 1
    for label in ("Составил", "Проверил", "Утвердил"):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=FIXED + 1)
        _cell(ws, r, 1, f"{label}: ____________________  /____________/  Дата: ____________", border=False)
        r += 2

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 52
    ws.column_dimensions["C"].width = 9
    ws.column_dimensions["D"].width = 11
    for c in price_cols:
        ws.column_dimensions[L(c)].width = 15
    for c in sum_cols:
        ws.column_dimensions[L(c)].width = 18
    ws.freeze_panes = ws.cell(row=first, column=FIXED + 1)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{H1}:{H2}"
    ws.print_area = f"A1:{L(last_col)}{r}"
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.5)
    ws.oddFooter.center.text = "Стр. &P из &N"

    # ---- detail sheets ----
    d = wb.create_sheet("Детализация товаров")
    d.append(["№", "Наименование", "Артикул", "Характеристики", "Ед.", "Кол-во", "Производитель", "Аналоги допускаются", "Доп. требования"])
    for i, it in enumerate(items, 1):
        d.append([i, it["name"], it.get("code"), it.get("specs"), it["unit"], it["quantity"], it.get("manufacturer"), "да" if it.get("analogs_allowed") else "нет", it.get("requirements")])
    q = wb.create_sheet("Коммерческие предложения")
    q.append(["Поставщик", "№ КП", "Дата", "Действует до", "Валюта", "Цены с НДС?", "Ставка НДС %", "Скидка %", "Доставка", "Срок, дн.", "Оплата", "Гарантия", "Статус", "Источники (id документов)"])
    for o in offers:
        q.append([o["supplier"], o.get("number"), o.get("date"), o.get("valid_until"), o["currency"],
                  {True: "да", False: "нет", None: "неизвестно"}[o.get("prices_include_vat")], o.get("vat_rate"), o.get("discount_pct"),
                  o.get("delivery_cost"), o.get("delivery_days"), o.get("payment_terms"), o.get("warranty"), o["status"], ", ".join(map(str, o.get("document_ids", [])))])
    rc = wb.create_sheet("Расчёты и курсы")
    rc.append(["Валюта", "Курс к " + cur, "Дата курса", "Источник"])
    for k, v in (p.get("rates") or {}).items():
        rc.append([k, v.get("rate"), v.get("date"), v.get("source")])
    rc.append([])
    rc.append(["Поставщик", "Позиция", "Цена в валюте оригинала", "Валюта оригинала", "Цена с НДС в " + cur, "Сумма"])
    for o in offers:
        for ln in o.get("lines", []):
            if ln.get("item_id") is None:
                continue
            it = next((x for x in items if x["id"] == ln["item_id"]), None)
            co = next((x for x in cmp_["offers"] if x["offer_id"] == o["id"]), None)
            cell = co["cells"].get(ln["item_id"]) if co else None
            rc.append([o["supplier"], it["name"] if it else ln["item_id"], ln.get("unit_price"), o["currency"],
                       cell["unit_price"].quantize(Decimal("0.01")) if cell and cell["status"] == "ok" else DASH,
                       cell["sum"].quantize(Decimal("0.01")) if cell and cell["status"] == "ok" else DASH])
    h = wb.create_sheet("История согласования")
    h.append(["Дата", "Из статуса", "В статус", "Пользователь", "Комментарий"])
    for e in data.get("history", []):
        h.append([e["at"].strftime("%d.%m.%Y %H:%M"), e["from"], e["to"], e["user"], e.get("comment")])
    for sh in (d, q, rc, h):
        for row in sh.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith('='):
                    c.data_type = 's'
        for row in sh.iter_rows(min_row=1, max_row=1):
            for c in row:
                c.font = Font(bold=True)
                c.fill = HEAD
        for col in sh.columns:
            sh.column_dimensions[col[0].column_letter].width = min(45, max(12, max(len(str(c.value or "")) for c in col) + 2))
        sh.page_setup.orientation = "landscape"
        sh.page_setup.fitToWidth = 1
        sh.page_setup.fitToHeight = 0
        sh.sheet_properties.pageSetUpPr.fitToPage = True

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
