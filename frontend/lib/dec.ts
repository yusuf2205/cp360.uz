/** Display-only exact decimal math (BigInt, 6 decimals). The server recomputes everything; this just shows live totals. */
const B = (n: number) => BigInt(n);
const ZERO = B(0), HUNDRED = B(100), S = B(1000000);

export function toMicro(v: string | null | undefined): bigint | null {
  if (v == null) return null;
  const s = String(v).trim().replace(/\s/g, "").replace(",", ".");
  if (!/^\d+(\.\d{0,6})?$/.test(s)) return null;
  const [i, d = ""] = s.split(".");
  return BigInt(i) * S + BigInt(d.padEnd(6, "0"));
}
export const mulM = (a: bigint, b: bigint) => (a * b) / S;

export function showMicro(n: bigint): string {
  const neg = n < ZERO;
  if (neg) n = -n;
  const cents = (n + B(5000)) / B(10000); // round half up to 2 places
  const i = (cents / HUNDRED).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const c = cents % HUNDRED;
  return (neg ? "-" : "") + i + (c === ZERO ? "" : "." + c.toString().padStart(2, "0"));
}

export function totals(lines: { qty: string; price: string }[], vatRatePct: string, pricesIncludeVat: boolean) {
  const rate = toMicro(vatRatePct) ?? ZERO;
  let sum = ZERO;
  for (const l of lines) {
    const q = toMicro(l.qty), p = toMicro(l.price);
    if (q != null && p != null) sum += mulM(q, p);
  }
  if (pricesIncludeVat) {
    const vat = (sum * rate) / (HUNDRED * S + rate);
    return { net: sum - vat, vat, gross: sum };
  }
  const vat = (sum * rate) / (HUNDRED * S);
  return { net: sum, vat, gross: sum + vat };
}
