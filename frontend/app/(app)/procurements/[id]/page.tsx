"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ComparisonTable from "@/components/ComparisonTable";
import WorkflowPanel from "@/components/WorkflowPanel";
import ImportPanel from "@/components/ImportPanel";
import { api, download, FLAG_RU, STATUS_RU } from "@/lib/api";

const inp = "rounded border border-black/20 dark:border-white/20 bg-transparent px-2 py-1 text-sm";
const TABS = ["Позиции", "Предложения", "Сравнение", "Согласование"];

export default function ProcurementPage() {
  const { id } = useParams<{ id: string }>();
  const pid = Number(id);
  const [p, setP] = useState<any>(null);
  const [tab, setTab] = useState(0);
  const [err, setErr] = useState("");
  const load = useCallback(() => api(`/api/procurements/${pid}`).then(setP).catch((e) => setErr(e.message)), [pid]);
  useEffect(() => { load(); }, [load]);
  if (err) return <p role="alert" className="text-red-600">{err}</p>;
  if (!p) return <div className="h-40 animate-pulse rounded bg-black/5 dark:bg-white/10" />;
  const editable = !p.locked;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{p.number}</h1>
        <span className="rounded-full bg-black/10 dark:bg-white/15 px-2 py-0.5 text-xs">{STATUS_RU[p.status]} · v{p.version}</span>
        <button className="ml-auto rounded bg-green-700 px-3 py-1.5 text-sm text-white" onClick={() => download(`/api/procurements/${pid}/export.xlsx`, `${p.number}.xlsx`).catch((e) => setErr(e.message))}>Скачать Excel</button>
      </div>
      {!editable && <p className="text-sm text-amber-600">Документ заблокирован. Для изменений создайте новую версию (вкладка «Согласование»).</p>}
      <div role="tablist" className="flex gap-1 border-b border-black/10 dark:border-white/15 overflow-x-auto">
        {TABS.map((t, i) => <button key={t} role="tab" aria-selected={tab === i} onClick={() => setTab(i)} className={`px-3 py-2 text-sm whitespace-nowrap ${tab === i ? "border-b-2 border-blue-600 font-medium" : "opacity-70"}`}>{t}</button>)}
      </div>
      {tab === 0 && <ItemsTab p={p} editable={editable} reload={load} />}
      {tab === 1 && <OffersTab p={p} editable={editable} reload={load} />}
      {tab === 2 && <CompareTab p={p} editable={editable} reload={load} />}
      {tab === 3 && <WorkflowTab p={p} reload={load} />}
    </div>
  );
}

function ItemsTab({ p, editable, reload }: any) {
  const empty = { name: "", unit: "т", quantity: "", specs: "" };
  const [f, setF] = useState(empty);
  const [meta, setMeta] = useState({ purpose: p.purpose ?? "", department: p.department ?? "", request_no: p.request_no ?? "", need_by: p.need_by ?? "", currency: p.currency });
  const [err, setErr] = useState("");
  const run = (fn: () => Promise<any>) => fn().then(() => { setErr(""); reload(); }).catch((e) => setErr(e.message));
  return (
    <div className="space-y-4">
      {editable && (
        <div className="grid sm:grid-cols-5 gap-2">
          <input aria-label="Назначение" className={`${inp} sm:col-span-2`} placeholder="Назначение закупки" value={meta.purpose} onChange={(e) => setMeta({ ...meta, purpose: e.target.value })} />
          <input aria-label="Подразделение" className={inp} placeholder="Подразделение" value={meta.department} onChange={(e) => setMeta({ ...meta, department: e.target.value })} />
          <input aria-label="Срок потребности" type="date" className={inp} value={meta.need_by} onChange={(e) => setMeta({ ...meta, need_by: e.target.value })} />
          <button className="rounded border px-3 py-1 text-sm" onClick={() => run(() => api(`/api/procurements/${p.id}`, { method: "PATCH", body: { ...meta, need_by: meta.need_by || null } }))}>Сохранить</button>
        </div>
      )}
      <table className="w-full text-sm"><thead><tr className="text-left border-b border-black/10 dark:border-white/15"><th>№</th><th>Наименование (ГОСТ, размеры, марка)</th><th>Ед.</th><th>Кол-во</th><th /></tr></thead>
        <tbody>{p.items.map((it: any, i: number) => <tr key={it.id} className="border-b border-black/5 dark:border-white/10 align-top"><td className="py-1">{i + 1}</td><td>{it.name}{it.specs && <div className="text-xs opacity-60">{it.specs}</div>}</td><td>{it.unit}</td><td>{it.quantity}</td>
          <td>{editable && <button className="text-red-600 text-xs" onClick={() => run(() => api(`/api/procurements/${p.id}/items/${it.id}`, { method: "DELETE" }))}>Удалить</button>}</td></tr>)}</tbody></table>
      {editable && (
        <form className="grid sm:grid-cols-6 gap-2" onSubmit={(e) => { e.preventDefault(); run(() => api(`/api/procurements/${p.id}/items`, { body: { ...f, specs: f.specs || null } }).then(() => setF(empty))); }}>
          <input required aria-label="Наименование" className={`${inp} sm:col-span-3`} placeholder="Наименование, например: Труба 57х3.5 ГОСТ 8732-78 ст20" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <input required aria-label="Единица" list="units" className={inp} placeholder="Ед." value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} />
          <datalist id="units">{["т", "кг", "м", "шт", "м2", "м3", "л", "компл"].map((u) => <option key={u} value={u} />)}</datalist>
          <input required aria-label="Количество" inputMode="decimal" className={inp} placeholder="Кол-во" value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value.replace(",", ".") })} />
          <button className="rounded bg-blue-600 px-3 py-1 text-sm text-white">+ Позиция</button>
        </form>
      )}
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
    </div>
  );
}

function OffersTab({ p, editable, reload }: any) {
  const [offers, setOffers] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const load = useCallback(() => api(`/api/procurements/${p.id}/offers`).then(setOffers), [p.id]);
  useEffect(() => { load(); }, [load]);
  const run = (fn: () => Promise<any>) => fn().then(() => { setErr(""); load(); reload(); }).catch((e) => setErr(typeof e.detail === "object" ? `${e.message}: ${(e.detail.flags ?? []).map((x: string) => FLAG_RU[x] ?? x).join("; ")}` : e.message));
  return (
    <div className="space-y-6">
      <ImportPanel pid={p.id} items={p.items} editable={editable} onChanged={() => { load(); reload(); }} />
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      {offers.map((o) => (
        <section key={o.id} className="rounded-lg border border-black/10 dark:border-white/15 p-3 space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="font-medium">{o.supplier}</h3>
            <span className="text-xs rounded-full bg-black/10 dark:bg-white/15 px-2 py-0.5">{o.status === "CONFIRMED" ? "Подтверждено" : "Требуется проверка"}</span>
            <span className="text-xs opacity-70">{o.currency} · {o.prices_include_vat == null ? "НДС не указан" : o.prices_include_vat ? "цены с НДС" : `без НДС (${o.vat_rate ?? "?"}%)`}</span>
            {editable && o.status !== "CONFIRMED" && <button className="ml-auto rounded bg-blue-600 px-2 py-1 text-xs text-white" onClick={() => run(() => api(`/api/offers/${o.id}/confirm`, { method: "POST" }))}>Подтвердить предложение</button>}
          </div>
          <table className="w-full text-xs"><tbody>{o.lines.map((l: any) => (
            <tr key={l.id} className="border-t border-black/5 dark:border-white/10 align-top">
              <td className="py-1 pr-2">{l.raw_name}</td><td>{l.quantity ?? "—"} {l.unit}</td><td>{l.unit_price ?? "—"}</td>
              <td className="pl-2">{l.item_id ? `поз. ${p.items.findIndex((i: any) => i.id === l.item_id) + 1}` : "нет в листе"} · {l.match_status}
                {l.tech_flags.length > 0 && <div className="text-red-600">{l.tech_flags.map((f: string) => FLAG_RU[f] ?? f).join("; ")}</div>}</td>
              <td className="text-right space-x-2 whitespace-nowrap">{editable && l.item_id && (l.match_status === "SUGGESTED") && <button className="underline" onClick={() => run(() => api(`/api/offer-lines/${l.id}/match`, { body: { item_id: l.item_id, status: "CONFIRMED" } }))}>Подтвердить</button>}
                {editable && l.item_id && l.match_status === "TECH_REVIEW" && <button className="underline text-amber-700" onClick={() => confirm("Принять как допустимый аналог несмотря на технические отличия?") && run(() => api(`/api/offer-lines/${l.id}/match`, { body: { item_id: l.item_id, status: "ANALOG_APPROVED" } }))}>Одобрить аналог</button>}</td>
            </tr>))}</tbody></table>
        </section>
      ))}
    </div>
  );
}

function CompareTab({ p, editable, reload }: any) {
  const [cmp, setCmp] = useState<any>(null);
  const [rule, setRule] = useState("none");
  const [rate, setRate] = useState({ currency: "USD", rate: "", date: new Date().toISOString().slice(0, 10), source: "" });
  const [sel, setSel] = useState({ supplier_id: "", reason: "" });
  const [err, setErr] = useState("");
  const load = useCallback(() => api(`/api/procurements/${p.id}/comparison?delivery_rule=${rule}`).then(setCmp).catch((e) => setErr(e.message)), [p.id, rule]);
  useEffect(() => { load(); }, [load]);
  const run = (fn: () => Promise<any>) => fn().then(() => { setErr(""); load(); reload(); }).catch((e) => setErr(e.message));
  if (!cmp) return <div className="h-32 animate-pulse rounded bg-black/5 dark:bg-white/10" />;
  return (
    <div className="space-y-5">
      <ComparisonTable items={p.items} cmp={cmp} selection={p.selection} />
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      {Object.keys(p.rates).length > 0 && <p className="text-xs opacity-70">Курсы: {Object.entries(p.rates).map(([c, r]: any) => `1 ${c} = ${r.rate} ${p.currency} (${r.date}, ${r.source})`).join("; ")}</p>}
      {editable && (
        <div className="grid md:grid-cols-2 gap-4">
          <form className="rounded border border-black/10 dark:border-white/15 p-3 space-y-2 text-sm" onSubmit={(e) => { e.preventDefault(); run(() => api(`/api/procurements/${p.id}/rates/${rate.currency}`, { method: "PUT", body: { rate: rate.rate, date: rate.date, source: rate.source } })); }}>
            <h3 className="font-medium">Курс валюты (к {p.currency})</h3>
            <div className="flex flex-wrap gap-2">
              <input aria-label="Валюта" maxLength={3} className={`${inp} w-16`} value={rate.currency} onChange={(e) => setRate({ ...rate, currency: e.target.value.toUpperCase() })} />
              <input aria-label="Курс" required inputMode="decimal" placeholder="Курс" className={`${inp} w-28`} value={rate.rate} onChange={(e) => setRate({ ...rate, rate: e.target.value.replace(",", ".") })} />
              <input aria-label="Дата курса" type="date" required className={inp} value={rate.date} onChange={(e) => setRate({ ...rate, date: e.target.value })} />
              <input aria-label="Источник курса" required placeholder="Источник (ЦБ РУз…)" className={`${inp} flex-1`} value={rate.source} onChange={(e) => setRate({ ...rate, source: e.target.value })} />
              <button className="rounded border px-3 py-1">Задать</button>
            </div>
          </form>
          <form className="rounded border border-black/10 dark:border-white/15 p-3 space-y-2 text-sm" onSubmit={(e) => { e.preventDefault(); run(() => api(`/api/procurements/${p.id}/selection`, { method: "PUT", body: { mode: "single", supplier_id: Number(sel.supplier_id), reason: sel.reason } })); }}>
            <h3 className="font-medium">Выбор поставщика (на всю закупку)</h3>
            <select required aria-label="Поставщик" className={`${inp} w-full`} value={sel.supplier_id} onChange={(e) => setSel({ ...sel, supplier_id: e.target.value })}>
              <option value="">— выберите —</option>{cmp.offers.map((o: any) => <option key={o.offer_id} value={o.supplier_id} disabled={!o.complete}>{o.supplier_name}{o.complete ? "" : " (неполное)"}</option>)}</select>
            <textarea required minLength={10} aria-label="Обоснование" placeholder="Обоснование выбора (опирайтесь на подтверждённые данные: цена, срок, соответствие требованиям)" className={`${inp} w-full`} rows={2} value={sel.reason} onChange={(e) => setSel({ ...sel, reason: e.target.value })} />
            <button className="rounded bg-blue-600 px-3 py-1 text-white">Зафиксировать выбор</button>
            {p.selection?.reason && <p className="text-xs opacity-70">Сейчас: {p.selection.reason}</p>}
          </form>
        </div>
      )}
      <label className="text-sm">Доставка: <select className={inp} value={rule} onChange={(e) => setRule(e.target.value)}><option value="none">не распределять по позициям</option><option value="by_value">пропорционально стоимости</option></select></label>
    </div>
  );
}

function WorkflowTab(props: any) { return <WorkflowPanel {...props} />; }
