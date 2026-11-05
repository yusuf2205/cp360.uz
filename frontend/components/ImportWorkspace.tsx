"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, FLAG_RU, fmt, STATUS_RU } from "@/lib/api";
import { ReviewEditor } from "./ImportPanel";
import ManualOffer from "./ManualOffer";
import SupplierLinks from "./SupplierLinks";

export default function ImportWorkspace({ p, reload }: { p: any; reload: () => void }) {
  const editable = !p.locked;
  const [docs, setDocs] = useState<any[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [tab, setTab] = useState<"text" | "manual" | "links">("text");
  const [pending, setPending] = useState(0);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  const [drag, setDrag] = useState(false);
  const [review, setReview] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api(`/api/imports?procurement_id=${p.id}`).then(setDocs).catch(() => {}), [p.id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!docs.some((d) => ["QUEUED", "ANALYZING"].includes(d.status))) return;
    const h = setInterval(load, 2000);
    return () => clearInterval(h);
  }, [docs, load]);
  const selDoc = docs.find((d) => d.id === sel);
  const selStatus = selDoc?.status;
  useEffect(() => {
    if (!sel || !selStatus || ["QUEUED", "ANALYZING"].includes(selStatus)) { setDetail(null); return; }
    api(`/api/imports/${sel}`).then(setDetail).catch(() => setDetail(null));
  }, [sel, selStatus]);

  async function upload(files: File[], pasted?: string) {
    if (!editable) return;
    const f = new FormData();
    f.append("procurement_id", String(p.id));
    files.forEach((x) => f.append("files", x));
    if (pasted) f.append("text", pasted);
    try {
      const res = await api("/api/imports", { form: f });
      const bad = res.filter((r: any) => r.error).map((r: any) => `${r.filename}: ${r.error}`);
      const dup = res.filter((r: any) => r.duplicate_upload).length;
      setMsg([bad.join("; "), dup ? `${dup} файл(ов) уже были загружены ранее` : ""].filter(Boolean).join(" · "));
      const first = res.find((r: any) => r.id);
      if (first) setSel(first.id);
      setText(""); load();
    } catch (e: any) { setMsg(e.message); }
  }
  function onPaste(e: React.ClipboardEvent) {
    const files = Array.from(e.clipboardData.files);
    if (files.length) { e.preventDefault(); upload(files.map((x, i) => (x.name === "image.png" ? new File([x], `clipboard-${Date.now()}-${i}.png`, { type: x.type }) : x))); }
  }

  if (review && sel) return <div className="card p-6"><ReviewEditor did={sel} pid={p.id} items={p.items} onClose={() => { setReview(false); load(); reload(); }} /></div>;

  const ex = detail?.extraction;
  return (
    <div className="grid gap-6 xl:grid-cols-[1.45fr_1fr]" onPaste={onPaste}>
      <section className="card">
        <div className="border-b border-line p-6"><h2 className="text-lg font-bold">Добавить коммерческое предложение</h2><p className="text-sm text-muted">Все предложения относятся к одной закупке</p></div>
        <div className="space-y-5 p-6">
          {editable && (
            <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); upload(Array.from(e.dataTransfer.files)); }}
              className={`rounded-2xl border-2 border-dashed p-10 text-center ${drag ? "border-primary bg-primary-soft" : "border-line bg-primary-soft/20"}`}>
              <div className="text-4xl text-primary">⇧</div>
              <div className="mt-3 text-lg font-bold">Перетащите файлы сюда</div>
              <div className="mt-1 text-sm text-muted">Фото · PDF · Excel · Word · текст · Ctrl+V для картинки из буфера обмена</div>
              <button type="button" className="btn-primary mt-4" onClick={() => input.current?.click()}>+ Выбрать файлы</button>
              <input ref={input} type="file" multiple hidden onChange={(e) => { upload(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
            </div>
          )}
          {msg && <p role="status" className="text-sm text-amber-600">{msg}</p>}
          {docs.length > 0 && (
            <ul className="flex flex-wrap gap-2">
              {docs.map((d) => (
                <li key={d.id}><button onClick={() => setSel(d.id)} className={`rounded-xl border px-3 py-2 text-left text-sm ${sel === d.id ? "border-primary bg-primary-soft" : "border-line"}`}>
                  📎 {d.filename}<span className={`ml-2 text-xs ${d.status === "ERROR" ? "text-red-600" : "text-muted"}`}>{STATUS_RU[d.status]}</span></button></li>
              ))}
            </ul>
          )}
          <div className="inline-flex rounded-2xl bg-primary-soft/50 p-1.5" role="tablist">
            {([["text", "Вставить текст"], ["manual", "Вручную"], ["links", "Ссылка поставщику"]] as const).map(([k, l]) => (
              <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`rounded-xl px-4 py-2 text-sm font-semibold ${tab === k ? "bg-card text-primary shadow-sm" : "text-muted"}`}>{l}{k === "links" && pending > 0 && <span className="ml-2 rounded-full bg-primary px-2 py-0.5 text-xs text-white">{pending}</span>}</button>
            ))}
          </div>
          {tab === "text" ? (
            <div className="space-y-3">
              <div className="label-caps">Сообщение поставщика</div>
              <textarea aria-label="Сообщение поставщика" rows={6} className="field" placeholder="Вставьте текст коммерческого предложения или переписку (Telegram, WhatsApp, e-mail)…" value={text} onChange={(e) => setText(e.target.value)} />
              <button disabled={!text.trim() || !editable} className="btn-primary" onClick={() => upload([], text)}>Распознать</button>
            </div>
          ) : tab === "manual" ? <ManualOffer p={p} onDone={() => { reload(); }} /> : <SupplierLinks p={p} editable={editable} onPending={setPending} onAccepted={reload} />}
        </div>
      </section>

      <div className="space-y-4">
        <section className="card">
          <div className="border-b border-line p-6"><h2 className="text-lg font-bold">Предпросмотр данных</h2></div>
          <div className="p-6 text-sm">
            {!selDoc && <p className="text-muted">Здесь появятся данные после загрузки или выбора файла.</p>}
            {selDoc && ["QUEUED", "ANALYZING"].includes(selDoc.status) && <p className="text-muted" aria-busy="true">{STATUS_RU[selDoc.status]}…</p>}
            {selDoc?.status === "ERROR" && <div className="space-y-2"><p className="text-red-600">{selDoc.error}</p>{editable && <button className="btn" onClick={() => api(`/api/imports/${selDoc.id}/retry`, { method: "POST" }).then(load)}>Повторить</button>}</div>}
            {selDoc?.status === "PROCESSED" && <p className="text-muted">Файл уже добавлен в сравнение.</p>}
            {ex && selDoc?.status === "NEEDS_REVIEW" && (
              <div className="space-y-3">
                <div><div className="label-caps">Поставщик</div><div className="font-semibold">{ex.supplier?.name ?? <span className="text-muted">не определён</span>}{ex.supplier?.inn && <span className="ml-2 text-muted">ИНН {ex.supplier.inn}</span>}</div></div>
                <div className="grid grid-cols-2 gap-2 text-xs text-muted">
                  <div>НДС: {ex.offer?.prices_include_vat == null ? "не указано" : ex.offer.prices_include_vat ? "цены с НДС" : "без НДС"}</div>
                  <div>Срок: {ex.offer?.delivery_days ? `${ex.offer.delivery_days} дн.` : "—"}</div>
                </div>
                <ul className="divide-y divide-line">
                  {ex.lines.slice(0, 12).map((l: any, i: number) => (
                    <li key={i} className="py-2"><div className="font-medium">{l.name}</div>
                      <div className="text-xs text-muted">{l.quantity ?? "?"} {l.unit ?? ""} × <b className={l.unit_price ? "text-foreground" : "text-red-600"}>{l.unit_price ? fmt(l.unit_price) : "цена неизвестна"}</b></div>
                      {l.warnings.length > 0 && <div className="text-xs text-amber-600">{l.warnings.map((w: string) => FLAG_RU[w] ?? w).join("; ")}</div>}</li>))}
                </ul>
                {ex.lines.length > 12 && <p className="text-xs text-muted">… и ещё {ex.lines.length - 12}</p>}
                {ex.lines.length === 0 && <p className="text-amber-600">Позиции не распознаны. Попробуйте вкладку «Вручную».</p>}
                {editable && <button className="btn-primary w-full" onClick={() => setReview(true)}>Проверить и добавить в сравнение →</button>}
              </div>
            )}
          </div>
        </section>
        <div className="rounded-2xl border border-[var(--warn-line)] bg-[var(--warn-bg)] p-4 text-sm text-[var(--warn-text)]">
          ⓘ Можно загрузить Excel, Word, PDF (в том числе скан), текст и фото — программа сама прочитает цены. Голосовые сообщения пока не поддерживаются: пришлите текстом. Фото бывают нечёткими, поэтому всё прочитанное вы проверяете сами перед добавлением. Если цены нет, поле остаётся пустым — программа ничего не додумывает.
        </div>
      </div>
    </div>
  );
}
