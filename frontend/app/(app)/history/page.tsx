"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fmt } from "@/lib/api";

type Row = { item: string; unit: string; supplier: string; unit_price: string; currency: string; prices_include_vat: boolean | null; vat_rate: string | null; date: string | null; procurement_id: number; procurement: string };

export default function HistoryPage() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (q.trim().length < 2) { setRows(null); return; }
    const h = setTimeout(() => api(`/api/history/prices?q=${encodeURIComponent(q.trim())}`).then((r) => { setRows(r); setErr(""); }).catch((e) => setErr(e.message)), 300);
    return () => clearTimeout(h);
  }, [q]);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-3xl font-extrabold">История цен</h1>
        <p className="mt-1 text-muted">Начните вводить название товара, и вы увидите, у кого и за сколько покупали раньше.</p>
      </header>
      <input autoFocus aria-label="Название товара" className="field !min-h-14 w-full !text-lg" placeholder="Например: труба, лист, цемент…" value={q} onChange={(e) => setQ(e.target.value)} />
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      {rows && rows.length === 0 && <p className="card p-6 text-muted">Ничего не найдено. В истории только подтверждённые предложения из уже сравнённых закупок.</p>}
      {rows && rows.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs uppercase text-muted"><th className="p-3">Товар</th><th className="p-3">Поставщик</th><th className="p-3 text-right">Цена за {rows[0].unit}</th><th className="p-3">НДС</th><th className="p-3">Дата</th><th className="p-3">Закупка</th></tr></thead>
            <tbody>{rows.map((r, i) => (
              <tr key={i} className="border-t border-line">
                <td className="p-3">{r.item}</td><td className="p-3 font-semibold">{r.supplier}</td>
                <td className="p-3 text-right tabular-nums font-bold">{fmt(r.unit_price)} <span className="text-xs font-normal text-muted">{r.currency}</span></td>
                <td className="p-3 text-xs">{r.prices_include_vat === null ? "не указано" : r.prices_include_vat ? "с НДС" : `без НДС${r.vat_rate ? ` (${r.vat_rate}%)` : ""}`}</td>
                <td className="p-3 text-xs text-muted">{r.date ? new Date(r.date).toLocaleDateString("ru-RU") : "—"}</td>
                <td className="p-3"><Link className="text-primary underline" href={`/procurements/${r.procurement_id}`}>{r.procurement}</Link></td>
              </tr>))}</tbody>
          </table>
          <p className="border-t border-line p-3 text-xs text-muted">Цены показаны так, как их назвал поставщик. Цены в разных валютах и с НДС или без НДС напрямую сравнивать нельзя, поэтому программа их не усредняет.</p>
        </div>
      )}
    </div>
  );
}
