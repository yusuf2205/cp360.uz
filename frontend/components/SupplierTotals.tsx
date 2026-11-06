"use client";
import { useState } from "react";
import { api, fmt, FLAG_RU } from "@/lib/api";

export default function SupplierTotals({ p, cmp, editable, rule, setRule, reload }: { p: any; cmp: any; editable: boolean; rule: string; setRule: (r: string) => void; reload: () => void }) {
  const [rate, setRate] = useState({ currency: "USD", rate: "", date: new Date().toISOString().slice(0, 10), source: "" });
  const [pick, setPick] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const run = (fn: () => Promise<any>) => fn().then(() => { setErr(""); setPick(null); setReason(""); reload(); }).catch((e) => setErr(e.message));
  const sel = p.selection?.supplier_id;
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  async function refreshCbu() {
    setBusy(true); setNote(""); setErr("");
    try {
      const r = await api(`/api/procurements/${p.id}/rates/refresh`, { method: "POST" });
      setNote(r.updated.length ? `Курс обновлён: ${r.updated.join(", ")}.` : "Нужных валют нет.");
      if (r.missing.length) setNote((n) => `${n} В списке Центробанка нет: ${r.missing.join(", ")}. Впишите курс вручную.`);
      reload();
    } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cmp.offers.map((o: any) => (
          <section key={o.offer_id} className={`card p-5 ${sel === o.supplier_id ? "ring-2 ring-primary" : ""}`}>
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-lg font-bold">{o.supplier_name}</h3>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${o.complete ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200" : "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200"}`}>
                {o.complete ? "Полное" : `Нет ${o.missing_items.length} поз.`}
              </span>
            </div>
            <div className={`mt-3 text-2xl font-extrabold tabular-nums ${o.offer_id === cmp.cheapest_complete_offer_id ? "text-good" : ""}`}>{fmt(o.items_total)} <span className="text-sm font-medium text-muted">{cmp.currency}</span></div>
            <dl className="mt-3 space-y-1 text-sm text-muted">
              <div className="flex justify-between"><dt>Отклонение от лучшего полного</dt><dd>{o.diff_vs_cheapest_pct == null ? "—" : `${Number(o.diff_vs_cheapest_pct).toFixed(1)} %`}</dd></div>
              <div className="flex justify-between"><dt>Срок поставки</dt><dd>{o.delivery_days != null ? `${o.delivery_days} дн.` : "—"}</dd></div>
              <div className="flex justify-between"><dt>Доставка</dt><dd>{fmt(o.delivery)}</dd></div>
            </dl>
            {o.flags.length > 0 && <p className="mt-3 text-xs text-amber-600">{o.flags.map((f: string) => FLAG_RU[f] ?? f).join("; ")}</p>}
            {sel === o.supplier_id && <p className="mt-3 text-xs"><b>Выбран.</b> {p.selection.reason}</p>}
            {editable && o.complete && sel !== o.supplier_id && (
              pick === o.supplier_id ? (
                <div className="mt-3 space-y-2">
                  <textarea aria-label="Обоснование выбора" minLength={10} rows={3} className="field" placeholder="Обоснование (цена, срок, соответствие требованиям — только подтверждённые данные)" value={reason} onChange={(e) => setReason(e.target.value)} />
                  <div className="flex gap-2">
                    <button disabled={reason.trim().length < 10} className="btn-primary" onClick={() => run(() => api(`/api/procurements/${p.id}/selection`, { method: "PUT", body: { mode: "single", supplier_id: o.supplier_id, reason } }))}>Зафиксировать</button>
                    <button className="btn" onClick={() => setPick(null)}>Отмена</button>
                  </div>
                </div>
              ) : <button className="btn mt-4 w-full" onClick={() => setPick(o.supplier_id)}>Выбрать поставщика</button>
            )}
          </section>
        ))}
      </div>
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card p-5 text-sm">
          <h3 className="mb-3 font-bold">Курс валюты (к {p.currency})</h3>
          {Object.keys(p.rates).length > 0 && <p className="mb-3 text-xs text-muted">{Object.entries(p.rates).map(([c, r]: any) => `1 ${c} = ${r.rate} ${p.currency} (${r.date}, ${r.source})`).join("; ")}</p>}
          {editable && (
            <div className="mb-3">
              <button type="button" disabled={busy} className="btn-primary" onClick={refreshCbu}>{busy ? "Загружаю…" : "Взять курс Центробанка"}</button>
              {note && <p role="status" className="mt-2 text-xs">{note}</p>}
            </div>
          )}
          {editable && (
            <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); run(() => api(`/api/procurements/${p.id}/rates/${rate.currency}`, { method: "PUT", body: { rate: rate.rate, date: rate.date, source: rate.source } })); }}>
              <input aria-label="Валюта" maxLength={3} className="field !w-16" value={rate.currency} onChange={(e) => setRate({ ...rate, currency: e.target.value.toUpperCase() })} />
              <input aria-label="Курс" required inputMode="decimal" placeholder="Курс" className="field !w-28" value={rate.rate} onChange={(e) => setRate({ ...rate, rate: e.target.value.replace(",", ".") })} />
              <input aria-label="Дата курса" type="date" required className="field !w-40" value={rate.date} onChange={(e) => setRate({ ...rate, date: e.target.value })} />
              <input aria-label="Источник курса" required placeholder="Источник (ЦБ РУз…)" className="field min-w-40 flex-1" value={rate.source} onChange={(e) => setRate({ ...rate, source: e.target.value })} />
              <button className="btn">Задать</button>
            </form>
          )}
        </section>
        <section className="card p-5 text-sm">
          <h3 className="mb-3 font-bold">Доставка</h3>
          <select aria-label="Распределение доставки" className="field" value={rule} onChange={(e) => setRule(e.target.value)}>
            <option value="none">не распределять по позициям</option>
            <option value="by_value">пропорционально стоимости позиций</option>
          </select>
        </section>
      </div>
    </div>
  );
}
