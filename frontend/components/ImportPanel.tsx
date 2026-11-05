"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, FLAG_RU, STATUS_RU } from "@/lib/api";

export default function ImportPanel({ pid, items, editable, onChanged }: { pid: number; items: any[]; editable: boolean; onChanged: () => void }) {
  const [docs, setDocs] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  const [drag, setDrag] = useState(false);
  const [review, setReview] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api(`/api/imports?procurement_id=${pid}`).then(setDocs).catch(() => {}), [pid]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!docs.some((d) => ["QUEUED", "ANALYZING"].includes(d.status))) return;
    const h = setInterval(load, 2000);
    return () => clearInterval(h);
  }, [docs, load]);

  async function upload(files: File[], pasted?: string) {
    const f = new FormData();
    f.append("procurement_id", String(pid));
    files.forEach((x) => f.append("files", x));
    if (pasted) f.append("text", pasted);
    try {
      const res = await api("/api/imports", { form: f });
      const bad = res.filter((r: any) => r.error).map((r: any) => `${r.filename}: ${r.error}`);
      const dup = res.filter((r: any) => r.duplicate_upload).length;
      setMsg([bad.join("; "), dup ? `${dup} файл(ов) уже загружены ранее` : ""].filter(Boolean).join(" · "));
      setText("");
      load();
    } catch (e: any) { setMsg(e.message); }
  }

  // paste an image / text from the clipboard anywhere on the panel
  function onPaste(e: React.ClipboardEvent) {
    const files = Array.from(e.clipboardData.files);
    if (files.length) { e.preventDefault(); upload(files.map((f, i) => (f.name === "image.png" ? new File([f], `clipboard-${Date.now()}-${i}.png`, { type: f.type }) : f))); }
  }

  if (review !== null) return <ReviewEditor did={review} pid={pid} items={items} onClose={() => { setReview(null); load(); onChanged(); }} />;

  return (
    <div className="space-y-4" onPaste={editable ? onPaste : undefined}>
      {editable && (
        <>
          <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); upload(Array.from(e.dataTransfer.files)); }}
            onClick={() => input.current?.click()} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
            className={`cursor-pointer rounded-xl border-2 border-dashed p-8 text-center text-sm ${drag ? "border-blue-500 bg-blue-500/10" : "border-black/20 dark:border-white/25"}`}>
            Перетащите файлы сюда, нажмите для выбора или вставьте изображение из буфера (Ctrl+V)
            <div className="opacity-60 mt-1">PDF, фото, Excel, Word, текст, аудио</div>
            <input ref={input} type="file" multiple hidden onChange={(e) => { upload(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
          </div>
          <div className="flex gap-2">
            <textarea aria-label="Вставить текст предложения" placeholder="Вставьте текст коммерческого предложения или переписку…" value={text} onChange={(e) => setText(e.target.value)} rows={3}
              className="flex-1 rounded border border-black/20 dark:border-white/20 bg-transparent p-2 text-sm" />
            <button disabled={!text.trim()} onClick={() => upload([], text)} className="self-end rounded bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50">Распознать</button>
          </div>
        </>
      )}
      {msg && <p role="status" className="text-sm text-amber-600">{msg}</p>}
      <table className="w-full text-sm">
        <thead><tr className="text-left border-b border-black/10 dark:border-white/15"><th className="py-2">Файл</th><th>Статус</th><th /></tr></thead>
        <tbody>{docs.map((d) => (
          <tr key={d.id} className="border-b border-black/5 dark:border-white/10">
            <td className="py-2">{d.filename}</td>
            <td>{STATUS_RU[d.status]}{d.error && <div className="text-xs text-red-600">{d.error}</div>}</td>
            <td className="text-right space-x-3">
              {d.status === "NEEDS_REVIEW" && <button className="text-blue-600 underline" onClick={() => setReview(d.id)}>Проверить</button>}
              {d.status === "ERROR" && editable && <button className="underline" onClick={() => api(`/api/imports/${d.id}/retry`, { method: "POST" }).then(load)}>Повторить</button>}
            </td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

const inp = "w-full rounded border border-black/20 dark:border-white/20 bg-transparent px-2 py-1 text-sm";

export function ReviewEditor({ did, pid, items, onClose }: { did: number; pid: number; items: any[]; onClose: () => void }) {
  const [d, setD] = useState<any>(null);
  const [offer, setOffer] = useState<any>({});
  const [lines, setLines] = useState<any[]>([]);
  const [supplierId, setSupplierId] = useState<string>("new");
  const [newSup, setNewSup] = useState<any>({ name: "", inn: "" });
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [err, setErr] = useState<any>(null);
  const [focus, setFocus] = useState<number | null>(null);

  useEffect(() => {
    api("/api/suppliers").then(setSuppliers);
    api(`/api/imports/${did}`).then((r) => {
      setD(r);
      const ex = r.extraction;
      setOffer({ ...ex.offer, currency: ex.offer.currency ?? "UZS" });
      setNewSup({ name: ex.supplier?.name ?? "", inn: ex.supplier?.inn ?? "", contacts: { phone: ex.supplier?.phone, email: ex.supplier?.email } });
      setSupplierId(r.supplier_candidates?.[0] ? String(r.supplier_candidates[0].id) : "new");
      setLines(ex.lines.map((l: any, i: number) => ({ ...l, src_index: i, item_id: r.line_suggestions[i].item_id, flags: r.line_suggestions[i].flags, score: r.line_suggestions[i].score, confirm_match: false, keep: true })));
    });
  }, [did]);

  if (!d) return <div className="h-40 animate-pulse rounded bg-black/5 dark:bg-white/10" />;
  const set = (i: number, k: string, v: any) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const lowConf = (l: any) => l.confidence < 0.6 || l.warnings.length > 0;
  const dupIdx = new Set<number>(d.possible_duplicate_lines.flat());

  async function apply() {
    setErr(null);
    const body: any = {
      offer: { ...offer, delivery_days: offer.delivery_days ? Number(offer.delivery_days) : null },
      lines: lines.filter((l) => l.keep).map((l) => ({ name: l.name, unit: l.unit || null, quantity: l.quantity || null, unit_price: l.unit_price || null, item_id: l.item_id || null, confirm_match: !!l.confirm_match, src_index: l.src_index })),
    };
    if (supplierId === "new") body.new_supplier = newSup; else body.supplier_id = Number(supplierId);
    try { await api(`/api/imports/${did}/apply`, { body }); onClose(); }
    catch (e: any) { setErr(e); }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3"><button onClick={onClose} className="underline text-sm">← Назад</button><h2 className="font-medium">Проверка: {d.filename}</h2></div>
      {d.extraction.warnings.length > 0 && <p className="text-sm text-amber-600">⚠ {d.extraction.warnings.map((w: string) => FLAG_RU[w] ?? w).join("; ")}</p>}
      <div className="grid lg:grid-cols-2 gap-4">
        <section aria-label="Оригинал" className="rounded border border-black/10 dark:border-white/15 p-3 max-h-[70vh] overflow-auto">
          <h3 className="text-sm font-medium mb-2">Оригинал (распознанный текст)</h3>
          <a className="text-xs text-blue-600 underline" href={`#`} onClick={async (e) => { e.preventDefault(); const r = await fetch(`/api/imports/${did}/original`, { headers: { Authorization: `Bearer ${localStorage.getItem("pp_token")}` } }); window.open(URL.createObjectURL(await r.blob())); }}>Открыть исходный файл</a>
          <pre className="mt-2 whitespace-pre-wrap text-xs">{(d.text as string).split("\n").map((ln, i) => {
            const snip = focus !== null ? lines[focus]?.source?.snippet : null;
            return <span key={i} className={snip && ln.length > 3 && (snip.includes(ln.slice(0, 40)) || ln.includes(snip.slice(0, 40))) ? "bg-yellow-300 dark:bg-yellow-700" : ""}>{ln}{"\n"}</span>;
          })}</pre>
        </section>
        <section className="space-y-3">
          <div className="rounded border border-black/10 dark:border-white/15 p-3 space-y-2">
            <h3 className="text-sm font-medium">Поставщик</h3>
            <select aria-label="Поставщик" className={inp} value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
              <option value="new">+ Новый поставщик</option>
              {d.supplier_candidates.map((c: any) => <option key={c.id} value={c.id}>Похожий: {c.name} ({c.inn ?? "—"})</option>)}
              {suppliers.filter((s) => !d.supplier_candidates.some((c: any) => c.id === s.id)).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {supplierId === "new" && <div className="grid grid-cols-2 gap-2"><input className={inp} placeholder="Название" value={newSup.name} onChange={(e) => setNewSup({ ...newSup, name: e.target.value })} /><input className={inp} placeholder="ИНН" value={newSup.inn ?? ""} onChange={(e) => setNewSup({ ...newSup, inn: e.target.value })} /></div>}
          </div>
          <div className="rounded border border-black/10 dark:border-white/15 p-3 grid grid-cols-2 gap-2 text-sm">
            <label>№ КП<input className={inp} value={offer.number ?? ""} onChange={(e) => setOffer({ ...offer, number: e.target.value })} /></label>
            <label>Валюта<input className={inp} maxLength={3} value={offer.currency ?? ""} onChange={(e) => setOffer({ ...offer, currency: e.target.value.toUpperCase() })} /></label>
            <label className={offer.prices_include_vat == null ? "text-red-600" : ""}>Цены с НДС?
              <select className={inp} value={offer.prices_include_vat == null ? "" : String(offer.prices_include_vat)} onChange={(e) => setOffer({ ...offer, prices_include_vat: e.target.value === "" ? null : e.target.value === "true" })}>
                <option value="">— не указано —</option><option value="true">Да, цены с НДС</option><option value="false">Нет, без НДС</option></select></label>
            <label>Ставка НДС, %<input className={inp} value={offer.vat_rate ?? ""} onChange={(e) => setOffer({ ...offer, vat_rate: e.target.value || null })} /></label>
            <label>Срок поставки, дн.<input className={inp} value={offer.delivery_days ?? ""} onChange={(e) => setOffer({ ...offer, delivery_days: e.target.value })} /></label>
            <label>Условия оплаты<input className={inp} value={offer.payment_terms ?? ""} onChange={(e) => setOffer({ ...offer, payment_terms: e.target.value })} /></label>
          </div>
        </section>
      </div>
      <div className="overflow-x-auto"><table className="w-full text-sm">
        <thead><tr className="text-left border-b border-black/10 dark:border-white/15"><th>✓</th><th>Наименование (из КП)</th><th>Ед.</th><th>Кол-во</th><th>Цена</th><th>Позиция в листе</th></tr></thead>
        <tbody>{lines.map((l, i) => (
          <tr key={i} onFocus={() => setFocus(i)} className={`border-b border-black/5 dark:border-white/10 align-top ${lowConf(l) ? "bg-amber-100/60 dark:bg-amber-900/30" : ""} ${dupIdx.has(i) ? "outline outline-1 outline-purple-500" : ""}`}>
            <td><input type="checkbox" aria-label="Включить строку" checked={l.keep} onChange={(e) => set(i, "keep", e.target.checked)} /></td>
            <td className="min-w-64"><textarea className={inp} rows={2} value={l.name} onChange={(e) => set(i, "name", e.target.value)} />
              <div className="text-xs text-amber-700 dark:text-amber-400">{l.warnings.map((w: string) => FLAG_RU[w] ?? w).join("; ")}{dupIdx.has(i) && " · возможный дубль"}</div></td>
            <td><input className={`${inp} w-16`} value={l.unit ?? ""} onChange={(e) => set(i, "unit", e.target.value)} /></td>
            <td><input className={`${inp} w-24`} value={l.quantity ?? ""} onChange={(e) => set(i, "quantity", e.target.value)} /></td>
            <td><input className={`${inp} w-28 ${!l.unit_price ? "border-red-500" : ""}`} placeholder="неизвестно" value={l.unit_price ?? ""} onChange={(e) => set(i, "unit_price", e.target.value)} /></td>
            <td className="min-w-56">
              <select className={inp} value={l.item_id ?? ""} onChange={(e) => setLines((ls) => ls.map((x, j) => j === i ? { ...x, item_id: e.target.value ? Number(e.target.value) : null, confirm_match: !!e.target.value } : x))}>
                <option value="">— нет в листе —</option>{items.map((it, n) => <option key={it.id} value={it.id}>{n + 1}. {it.name.slice(0, 50)}</option>)}</select>
              {l.item_id && <label className="text-xs flex gap-1 mt-1"><input type="checkbox" checked={l.confirm_match} onChange={(e) => set(i, "confirm_match", e.target.checked)} />Сопоставление верно</label>}
              {l.item_id && l.flags?.length > 0 && <div className="text-xs text-red-600">Техническая проверка: {l.flags.map((f: string) => FLAG_RU[f] ?? f).join("; ")}</div>}
            </td>
          </tr>))}</tbody></table></div>
      {err && <div role="alert" className="text-sm text-red-600">{err.message}{err.detail?.duplicates && <> — {err.detail.duplicates.map((x: any) => x.name).join(", ")}; выберите существующего поставщика</>}</div>}
      <div className="flex gap-2"><button onClick={apply} className="rounded bg-blue-600 px-4 py-2 text-sm text-white">Подтвердить и добавить в сравнение</button><button onClick={onClose} className="rounded border px-4 py-2 text-sm">Отмена</button></div>
    </div>
  );
}
