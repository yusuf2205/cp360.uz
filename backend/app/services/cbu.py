"""Official exchange rates of the Central Bank of Uzbekistan (cbu.uz). Fetched only when a buyer presses the button."""
from datetime import date, datetime
from decimal import Decimal

import httpx

CBU_URL = "https://cbu.uz/ru/arkhiv-kursov-valyut/json/"


class RatesUnavailable(Exception):
    pass


def fetch_cbu() -> dict[str, tuple[Decimal, date]]:
    """currency -> (UZS per 1 unit, date of the rate)."""
    try:
        r = httpx.get(CBU_URL, timeout=15, follow_redirects=True)
        r.raise_for_status()
        rows = r.json()
        out = {}
        for x in rows:
            nominal = Decimal(str(x.get("Nominal") or "1")) or Decimal(1)
            out[str(x["Ccy"]).upper()] = (Decimal(str(x["Rate"]).replace(",", ".")) / nominal, datetime.strptime(x["Date"], "%d.%m.%Y").date())
        if not out:
            raise ValueError("empty")
        return out
    except Exception as e:  # noqa: BLE001
        raise RatesUnavailable(type(e).__name__) from e


def rates_for(base: str, wanted: list[str], table: dict[str, tuple[Decimal, date]]) -> tuple[dict, list[str]]:
    """Rates in the procurement's own currency: units of `base` per 1 unit of each wanted currency. Returns (rates, missing)."""
    base = base.upper()
    uzs = lambda c: (Decimal(1), None) if c == "UZS" else table.get(c)  # noqa: E731
    b = uzs(base)
    out, missing = {}, []
    for c in wanted:
        c = c.upper()
        v = uzs(c)
        if c == base:
            continue
        if not v or not b:
            missing.append(c)
            continue
        d = v[1] or b[1] or date.today()
        out[c] = {"rate": format((v[0] / b[0]).quantize(Decimal("0.000001")).normalize(), "f"), "date": d.isoformat(), "source": "ЦБ Узбекистана"}
    return out, missing
