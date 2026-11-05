"use client";
import { fmt, FLAG_RU } from "@/lib/api";

/** Corporate layout: fixed left columns (name, unit, qty); per supplier two sub-columns (price with VAT / sum with VAT). */
export default function ComparisonTable({ items, cmp, selection, onDelete }: { items: any[]; cmp: any; selection: any; onDelete?: (id: number) => void }) {
  if (!cmp.offers.length) return <p className="px-6 pb-6 text-sm text-muted">Предложений пока нет. Добавьте их на шаге «Загрузка».</p>;
  const chosen = new Set<number>([selection?.supplier_id, ...Object.values(selection?.items ?? {})].filter(Boolean) as number[]);
  const head = "border-b border-line px-4 py-3 text-sm font-semibold text-muted";
  const cell = "whitespace-nowrap border-b border-line px-4 py-4 text-right tabular-nums";
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse text-sm">
        <thead>
          <tr>
            <th rowSpan={2} className={`${head} min-w-80 text-left`}>Наименование</th>
            <th rowSpan={2} className={`${head} text-center`}>Ед.</th>
            <th rowSpan={2} className={`${head} text-right`}>Кол.</th>
            {cmp.offers.map((o: any) => (
              <th key={o.offer_id} colSpan={2} className={`${head} border-l text-center ${chosen.has(o.supplier_id) ? "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100" : ""}`}>
                {o.supplier_name}
                {!o.complete && <div className="text-xs font-normal text-red-600">неполное предложение</div>}
              </th>
            ))}
          </tr>
          <tr>{cmp.offers.flatMap((o: any) => [
            <th key={o.offer_id + "p"} className={`${head} border-l text-right`}>Цена с НДС</th>,
            <th key={o.offer_id + "s"} className={`${head} text-right`}>Сумма с НДС</th>,
          ])}</tr>
        </thead>
        <tbody>
          {items.map((it) => {
            const best = cmp.best_per_item[it.id];
            return (
              <tr key={it.id} className="group hover:bg-primary-soft/30">
                <td className="border-b border-line px-4 py-4 font-medium">
                  {it.name}{it.specs && <div className="text-xs font-normal text-muted">{it.specs}</div>}
                  {onDelete && <button aria-label="Удалить позицию" title="Удалить позицию" onClick={() => confirm(`Удалить «${it.name}»?`) && onDelete(it.id)} className="ml-2 hidden text-xs text-red-600 group-hover:inline">✕</button>}
                </td>
                <td className="border-b border-line px-4 py-4 text-center">{it.unit}</td>
                <td className={cell}>{fmt(it.quantity)}</td>
                {cmp.offers.flatMap((o: any) => {
                  const c = o.cells[it.id];
                  const ok = c.status === "ok";
                  const isBest = ok && best && best.tied.includes(o.supplier_id);
                  const why = !ok && c.status !== "absent" ? c.status : undefined;
                  return [
                    <td key={o.offer_id + "p"} title={why} className={`${cell} border-l border-l-line ${isBest ? "font-bold text-good" : ""} ${!ok ? "text-muted" : ""}`}>{ok ? <>{isBest && <span aria-label="лучшая цена" title="Лучшая цена">★ </span>}{fmt(c.unit_price)}</> : "—"}</td>,
                    <td key={o.offer_id + "s"} className={`${cell} ${!ok ? "text-muted" : ""}`}>{ok ? fmt(c.sum) : "—"}</td>,
                  ];
                })}
              </tr>
            );
          })}
          <tr className="font-bold">
            <td colSpan={3} className={`${cell} !text-right`}>ИТОГО с НДС</td>
            {cmp.offers.flatMap((o: any) => [
              <td key={o.offer_id + "p"} className={`${cell} border-l border-l-line`} />,
              <td key={o.offer_id + "s"} className={`${cell} ${o.offer_id === cmp.cheapest_complete_offer_id ? "text-good" : ""}`}>{fmt(o.items_total)}</td>,
            ])}
          </tr>
        </tbody>
      </table>
      <div className="space-y-1 px-6 py-4 text-sm text-muted">
        <div><b>★ и зелёный</b> — самая низкая цена по товару. Зелёная итоговая сумма — самое дешёвое <b>полное</b> предложение (то, где есть цены на все товары). Все цены приведены к ценам с НДС ({cmp.currency}). Прочерк «—» — у поставщика нет этого товара; это не нулевая цена.</div>
        {cmp.split_total && <div>Закупка у нескольких поставщиков (лучшая цена по каждой позиции): <b className="text-foreground">{fmt(cmp.split_total)}</b>{cmp.split_savings_vs_cheapest_complete && <> · возможная экономия относительно лучшего полного предложения: <b className="text-foreground">{fmt(cmp.split_savings_vs_cheapest_complete)}</b></>}</div>}
        {cmp.warnings?.map((w: string) => <div key={w} className="text-amber-600">⚠ {FLAG_RU[w] ?? w}</div>)}
      </div>
    </div>
  );
}
