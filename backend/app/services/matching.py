"""Item matching. Only ever *suggests*: a human confirms; technical mismatches force TECH_REVIEW."""
import re
from difflib import SequenceMatcher

_X = "xх×*"  # latin x, cyrillic ha, multiplication sign, asterisk
DIM_RE = re.compile(rf"(\d+(?:[.,]\d+)?(?:\s*[{_X}]\s*\d+(?:[.,]\d+)?)+)")
GOST_RE = re.compile(r"(?:гост|gost|ост|ту|din|iso|en)\s*(?:р\s*)?(?:[\w.]+\s*)?[№n]?\s*(\d[\d.\-]*\d)", re.I)
GRADE_RE = re.compile(r"\b(\d{2}[а-яa-z]\d?[а-яa-z]?\d?|ст\.?\s?\d[а-я]{0,2}\d?|[авcab]\d{3}[a-z]?)\b", re.I)
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")

UNIT_CANON = {
    "т": "т", "тн": "т", "тонна": "т", "тонн": "т", "tn": "т", "t": "т", "ton": "т",
    "кг": "кг", "kg": "кг", "килограмм": "кг",
    "м": "м", "м.п": "м", "мп": "м", "пог.м": "м", "m": "м", "метр": "м", "метров": "м",
    "шт": "шт", "штук": "шт", "шт.": "шт", "pcs": "шт", "dona": "шт", "дона": "шт",
    "м2": "м2", "м²": "м2", "кв.м": "м2", "м3": "м3", "м³": "м3", "куб.м": "м3",
    "л": "л", "литр": "л", "компл": "компл", "комплект": "компл", "уп": "уп", "упак": "уп",
}


def canon_unit(u: str | None) -> str | None:
    if not u:
        return None
    k = u.strip().lower().rstrip(".").replace(" ", "")
    return UNIT_CANON.get(k, UNIT_CANON.get(k + ".", k))


def units_compatible(a: str | None, b: str | None) -> bool | None:
    ca, cb = canon_unit(a), canon_unit(b)
    if not ca or not cb:
        return None
    return ca == cb


def _clean(s: str) -> str:
    s = s.lower().replace("ё", "е").replace("²", "2").replace("³", "3")
    return s


def normalise(s: str) -> str:
    s = _clean(s)
    s = DIM_RE.sub(lambda m: re.sub(rf"\s*[{_X}]\s*", "x", m.group(1)).replace(",", "."), s)
    s = re.sub(r"[^\w.\-x]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def features(s: str) -> dict:
    t = _clean(s)
    dims = {re.sub(rf"\s*[{_X}]\s*", "x", d).replace(",", ".") for d in DIM_RE.findall(t)}
    gost = {g.rstrip(".-") for g in GOST_RE.findall(t)}
    grades = {re.sub(r"[\s.]", "", g) for g in GRADE_RE.findall(t)}
    rest = DIM_RE.sub(" ", t)
    rest = GOST_RE.sub(" ", rest)
    nums = {n.replace(",", ".") for n in NUM_RE.findall(rest)}
    return {"dims": dims, "gost": gost, "grades": grades, "nums": nums}


def tech_flags(requested: str, offered: str) -> list[str]:
    a, b = features(requested), features(offered)
    flags = []
    for key, label in (("dims", "dimensions"), ("gost", "standard"), ("grades", "material_grade")):
        if a[key] and b[key] and a[key] != b[key]:
            flags.append(f"{label}_mismatch")
        elif a[key] and not b[key]:
            flags.append(f"{label}_not_stated")
    if not a["dims"] and not b["dims"] and a["nums"] and b["nums"] and a["nums"] != b["nums"]:
        flags.append("numeric_parameters_differ")
    return flags


def similarity(a: str, b: str) -> float:
    na, nb = normalise(a), normalise(b)
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    jac = len(ta & tb) / len(ta | tb)
    seq = SequenceMatcher(None, na, nb).ratio()
    return round(0.5 * jac + 0.5 * seq, 4)


def suggest(requested_items: list[dict], offered_name: str, offered_unit: str | None = None, threshold: float = 0.45) -> dict:
    """requested_items: [{id,name,unit,specs?}]. Returns best candidate and ranked list.

    Status is never CONFIRMED here. Technical differences -> TECH_REVIEW, even for a high text score.
    """
    ranked = []
    for it in requested_items:
        req_text = f"{it['name']} {it.get('specs') or ''}".strip()
        score = similarity(req_text, offered_name)
        flags = tech_flags(req_text, offered_name)
        if units_compatible(it.get("unit"), offered_unit) is False:
            flags.append("unit_mismatch")
        ranked.append({"item_id": it["id"], "score": score, "flags": flags})
    ranked.sort(key=lambda r: r["score"], reverse=True)
    if not ranked or ranked[0]["score"] < threshold:
        return {"item_id": None, "score": ranked[0]["score"] if ranked else 0.0, "status": "UNMATCHED", "flags": [], "candidates": ranked[:3]}
    top = ranked[0]
    status = "TECH_REVIEW" if top["flags"] else "SUGGESTED"
    return {"item_id": top["item_id"], "score": top["score"], "status": status, "flags": top["flags"], "candidates": ranked[:3]}
