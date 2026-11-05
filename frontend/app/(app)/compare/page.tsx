"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ComparisonTable from "@/components/ComparisonTable";
import SupplierTotals from "@/components/SupplierTotals";
import { ActiveBar, NoActive, PageHead } from "@/components/Flow";
import { api, download } from "@/lib/api";
import { useActive } from "@/lib/active";

export default function ComparePage() {
  const { pid, set, ready } = useActive();
  const [p, setP] = useState<any>(null);
  const [cmp, setCmp] = useState<any>(null);
  const [tab, setTab] = useState<"prices" | "totals">("prices");
  const [rule, setRule] = useState("none");
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ name: "", unit: "т", quantity: "", specs: "" });
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    if (!pid) return;
    try {
      const [pp, c] = await Promise.all([api(`/api/procurements/${pid}`), api(`/api/procurements/${pid}/comparison?delivery_rule=${rule}`)]);
      setP(pp); setCmp(c); setErr("");
    } catch (e: any) {
      if (e.status === 404) set(null); else setErr(e.message);
    }
  }, [pid, rule, set]);
  useEffect(() => { load(); }, [load]);

  if (!ready) return null;
  if (!pid) return <><PageHead step={2} title="Сравнение предложений" /><NoActive onPick={set} /></>;
  if (!p || !cmp) return <div className="h-64 animate-pulse rounded-2xl bg-primary-soft/40" />;

  const editable = !p.locked;
  const incomplete = cmp.incomplete_offer_ids.length > 0;
  async function addItem(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/api/procurements/${pid}/items`, { body: { ...f, specs: f.specs || null } });
      setF({ name: "", unit: f.unit, quantity: "", specs: "" }); setAdding(false); load();
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <div>
      <PageHead step={2} title="Сравнение предложений"
        subtitle={`${p.purpose || "Без названия"} · ${p.number} · ${cmp.offers.length} ${cmp.offers.length === 1 ? "поставщик" : "поставщиков"}`}
        help="Здесь все предложения рядом. ★ и зелёный цвет — самая низкая цена по товару. Прочерк «—» значит, что у этого поставщика такого товара нет. Выбрать поставщика можно на вкладке «Итоги поставщиков»."
        right={<button className="btn-primary" onClick={() => download(`/api/procurements/${pid}/export.xlsx`, `${p.number}.xlsx`).catch((e) => setErr(e.message))}>⬇ Экспорт Excel →</button>} />
      <ActiveBar pid={pid} onPick={set} />
      {err && <p role="alert" className="mb-3 text-sm text-red-600">{err}</p>}
      {!editable && <p className="mb-3 text-sm text-amber-600">Документ заблокирован ({p.status}). Для изменений создайте новую версию на шаге «Excel».</p>}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-2xl bg-primary-soft/50 p-1.5" role="tablist">
          {([["prices", "Таблица цен"], ["totals", "Итоги поставщиков"]] as const).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`rounded-xl px-4 py-2 text-sm font-semibold ${tab === k ? "bg-card text-primary shadow-sm" : "text-muted"}`}>{l}</button>
          ))}
        </div>
        {incomplete && <span className="rounded-full bg-amber-100 px-4 py-1.5 text-xs font-bold text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">Есть неполные предложения</span>}
      </div>

      {tab === "prices" ? (
        <section className="card">
          <div className="flex flex-wrap items-center justify-between gap-3 p-6">
            <div><h2 className="text-lg font-bold">Сравнительный лист</h2><p className="text-sm text-muted">Все цены указаны с НДС, в валюте {cmp.currency}</p></div>
            {editable && <button className="btn" onClick={() => setAdding(!adding)}>+ Добавить товар</button>}
          </div>
          {adding && (
            <form onSubmit={addItem} className="grid gap-2 border-t border-line p-6 sm:grid-cols-6">
              <input required aria-label="Наименование" className="field sm:col-span-3" placeholder="Наименование, например: Лист ГК 4,0×1500×6000 ГОСТ 19903-2015" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
              <input required aria-label="Единица" list="units" className="field" placeholder="Ед." value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} />
              <datalist id="units">{["т", "кг", "м", "шт", "м2", "м3", "л", "компл"].map((u) => <option key={u} value={u} />)}</datalist>
              <input required aria-label="Количество" inputMode="decimal" className="field" placeholder="Кол-во" value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value.replace(",", ".") })} />
              <button className="btn-primary">Добавить</button>
            </form>
          )}
          {p.items.length === 0 ? <p className="px-6 pb-6 text-sm text-muted">Список товаров пуст. Добавьте позиции, затем загрузите предложения.</p> :
            <ComparisonTable items={p.items} cmp={cmp} selection={p.selection} onDelete={editable ? (id) => api(`/api/procurements/${pid}/items/${id}`, { method: "DELETE" }).then(load).catch((e) => setErr(e.message)) : undefined} />}
        </section>
      ) : (
        <SupplierTotals p={p} cmp={cmp} editable={editable} rule={rule} setRule={setRule} reload={load} />
      )}

      <div className="mt-6 flex justify-between">
        <Link className="btn" href="/import">← Загрузка</Link>
        <Link className="btn-primary" href="/export">Далее: Excel →</Link>
      </div>
    </div>
  );
}
