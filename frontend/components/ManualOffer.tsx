"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Manual entry: the user types the supplier's unit prices per requested item. Links are user-made, so they are confirmed. */
export default function ManualOffer({ p, onDone }: { p: any; onDone: () => void }) {
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [sid, setSid] = useState("new");
  const [name, setName] = useState("");
  const [vat, setVat] = useState("true");
  const [vatRate, setVatRate] = useState("12");
  const [days, setDays] = useState("");
  const [prices, setPrices] = useState<Record<number, string>>({});
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api("/api/suppliers").then(setSuppliers); }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      let supplierId: number | null = sid === "new" ? null : Number(sid);
      if (supplierId === null) supplierId = (await api("/api/suppliers", { body: { name } })).id;
      const lines = p.items.filter((i: any) => prices[i.id]).map((i: any) => ({ raw_name: i.name, unit: i.unit, quantity: i.quantity, unit_price: prices[i.id], item_id: i.id }));
      if (!lines.length) throw new Error("Укажите хотя бы одну цену");
      const o = await api(`/api/procurements/${p.id}/offers`, { body: { supplier_id: supplierId, currency: p.currency, prices_include_vat: vat === "true", vat_rate: vat === "true" ? null : vatRate, delivery_days: days ? Number(days) : null, lines } });
      for (const l of o.lines) await api(`/api/offer-lines/${l.id}/match`, { body: { item_id: l.item_id, status: "CONFIRMED" } });
      await api(`/api/offers/${o.id}/confirm`, { method: "POST" });
      setPrices({}); setName(""); setDays(""); onDone();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  if (!p.items.length) return <p className="text-sm text-muted">Сначала добавьте товары на шаге «Сравнение» (кнопка «+ Добавить товар»).</p>;
  return (
    <form onSubmit={save} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm"><span className="label-caps">Поставщик</span>
          <select className="field mt-1" value={sid} onChange={(e) => setSid(e.target.value)}><option value="new">+ Новый поставщик</option>{suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        {sid === "new" && <label className="text-sm"><span className="label-caps">Название</span><input required className="field mt-1" value={name} onChange={(e) => setName(e.target.value)} /></label>}
        <label className="text-sm"><span className="label-caps">Цены</span>
          <select className="field mt-1" value={vat} onChange={(e) => setVat(e.target.value)}><option value="true">с НДС</option><option value="false">без НДС</option></select></label>
        {vat === "false" && <label className="text-sm"><span className="label-caps">Ставка НДС, %</span><input className="field mt-1" value={vatRate} onChange={(e) => setVatRate(e.target.value)} /></label>}
        <label className="text-sm"><span className="label-caps">Срок поставки, дн.</span><input inputMode="numeric" className="field mt-1" value={days} onChange={(e) => setDays(e.target.value)} /></label>
      </div>
      <table className="w-full text-sm"><thead><tr className="text-left text-muted"><th className="py-1">Товар</th><th>Кол.</th><th className="w-40">Цена за ед.</th></tr></thead>
        <tbody>{p.items.map((i: any) => (
          <tr key={i.id} className="border-t border-line"><td className="py-2 pr-2">{i.name}</td><td className="whitespace-nowrap pr-2">{i.quantity} {i.unit}</td>
            <td><input aria-label={`Цена: ${i.name}`} inputMode="decimal" placeholder="нет предложения" className="field" value={prices[i.id] ?? ""} onChange={(e) => setPrices({ ...prices, [i.id]: e.target.value.replace(",", ".") })} /></td></tr>))}</tbody></table>
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      <button disabled={busy} className="btn-primary">Сохранить предложение</button>
    </form>
  );
}
