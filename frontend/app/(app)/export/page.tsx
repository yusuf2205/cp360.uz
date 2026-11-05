"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ActiveBar, NoActive, PageHead } from "@/components/Flow";
import WorkflowPanel from "@/components/WorkflowPanel";
import { api, download, fmt, STATUS_RU } from "@/lib/api";
import { useActive } from "@/lib/active";

export default function ExportPage() {
  const { pid, set, ready } = useActive();
  const [p, setP] = useState<any>(null);
  const [cmp, setCmp] = useState<any>(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    if (!pid) return;
    try {
      const [pp, c] = await Promise.all([api(`/api/procurements/${pid}`), api(`/api/procurements/${pid}/comparison`)]);
      setP(pp); setCmp(c);
    } catch (e: any) { if (e.status === 404) set(null); else setErr(e.message); }
  }, [pid, set]);
  useEffect(() => { load(); }, [load]);

  if (!ready) return null;
  if (!pid) return <><PageHead step={3} title="Экспорт Excel" /><NoActive onPick={set} /></>;
  if (!p || !cmp) return <div className="h-64 animate-pulse rounded-2xl bg-primary-soft/40" />;
  const winner = cmp.offers.find((o: any) => o.offer_id === cmp.cheapest_complete_offer_id);
  const chosen = cmp.offers.find((o: any) => o.supplier_id === p.selection?.supplier_id);

  return (
    <div>
      <PageHead step={3} title="Экспорт Excel" subtitle={`${p.purpose || "Без названия"} · ${p.number} · ${STATUS_RU[p.status]} · версия ${p.version}`}
        help="Последний шаг: проверьте сводку и скачайте Excel. Если документ нужно утвердить — отправьте его на согласование в блоке справа." />
      <ActiveBar pid={pid} onPick={set} />
      {err && <p role="alert" className="mb-3 text-sm text-red-600">{err}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card p-6">
          <h2 className="mb-1 text-lg font-bold">Готовый сравнительный лист</h2>
          <p className="mb-4 text-sm text-muted">Формулы в файле рабочие: сумма = количество × цена, итог = сумма по столбцу. Листы: сравнительный, детализация, КП, расчёты и курсы, история согласования.</p>
          <dl className="mb-5 space-y-1 text-sm">
            <div className="flex justify-between"><dt className="text-muted">Позиций</dt><dd>{p.items.length}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Поставщиков</dt><dd>{cmp.offers.length} (неполных: {cmp.incomplete_offer_ids.length})</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Лучшее полное предложение</dt><dd>{winner ? `${winner.supplier_name} — ${fmt(winner.items_total)}` : "нет"}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Выбранный поставщик</dt><dd>{chosen ? chosen.supplier_name : "не выбран"}</dd></div>
          </dl>
          {!p.selection?.reason && <p className="mb-3 text-sm text-amber-600">Выбор поставщика и обоснование ещё не зафиксированы (шаг «Сравнение → Итоги поставщиков»). Excel можно скачать и без них.</p>}
          <button className="btn-primary w-full !py-3" onClick={() => download(`/api/procurements/${pid}/export.xlsx`, `${p.number}.xlsx`).catch((e) => setErr(e.message))}>⬇ Скачать Excel</button>
        </section>
        <section className="card p-6">
          <h2 className="mb-3 text-lg font-bold">Согласование</h2>
          <WorkflowPanel p={p} reload={load} />
        </section>
      </div>
      <div className="mt-6"><Link className="btn" href="/compare">← Сравнение</Link></div>
    </div>
  );
}
