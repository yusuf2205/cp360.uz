"use client";
import { useCallback, useEffect, useState } from "react";
import { api, fmt } from "@/lib/api";
import ShareLink from "./ShareLink";

const STATUS: Record<string, [string, string]> = {
  WAITING: ["Ожидает ответа", "bg-primary-soft text-primary"],
  NEW: ["Ответ получен", "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"],
  ACCEPTED: ["Добавлено в сравнение", "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200"],
  REJECTED: ["Отклонено", "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200"],
  EXPIRED: ["Срок истёк", "bg-black/10 text-muted"],
  REVOKED: ["Отозвана", "bg-black/10 text-muted"],
};

function daysSince(iso: string) {
  const t = Date.parse(/Z|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z");
  return Number.isFinite(t) ? Math.max(0, Math.floor((Date.now() - t) / 86400000)) : 0;
}

/** One tap to nudge a supplier who has not answered: same link, a polite reminder text, same channels. */
function Reminder({ r, p, link }: { r: any; p: any; link: string }) {
  const [open, setOpen] = useState(false);
  const d = daysSince(r.created_at);
  const late = d >= 1;
  return (
    <div className="mt-3">
      <button type="button" className={late ? "btn-primary" : "btn"} onClick={() => setOpen(!open)} aria-expanded={open}>
        🔔 Напомнить поставщику{late ? ` · нет ответа ${d} дн.` : ""}
      </button>
      {open && (
        <ShareLink url={link} who={r.supplier_hint || undefined} subject={`Напоминание: коммерческое предложение ${p.number}`}
          text={`Здравствуйте! Напоминаем о запросе коммерческого предложения по закупке ${p.number}. Пожалуйста, заполните короткую форму по ссылке, это займёт 2–3 минуты:`} />
      )}
    </div>
  );
}

export default function SupplierLinks({ p, editable, onPending, onAccepted }: { p: any; editable: boolean; onPending: (n: number) => void; onAccepted: () => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const [f, setF] = useState({ name: "", days: "7", vat: "12", message: "" });
  const [err, setErr] = useState("");
  const [dups, setDups] = useState<{ sid: number; list: any[] } | null>(null);

  const load = useCallback(() => api(`/api/procurements/${p.id}/invitations`).then((r) => { setRows(r); onPending(r.filter((x: any) => x.submission?.status === "NEW").length); }).catch(() => {}), [p.id, onPending]);
  useEffect(() => { load(); const h = setInterval(load, 15000); return () => clearInterval(h); }, [load]);

  const url = (t: string) => `${window.location.origin}/rfq/${t}`;
  const run = (fn: () => Promise<any>) => fn().then(() => { setErr(""); setDups(null); load(); }).catch((e) => setErr(e.message));

  async function create(e: React.FormEvent) {
    e.preventDefault();
    run(() => api(`/api/procurements/${p.id}/invitations`, { body: { supplier_name: f.name || null, valid_days: Number(f.days), vat_rate_default: f.vat || null, message: f.message || null } }).then(() => setF({ ...f, name: "", message: "" })));
  }
  async function accept(subId: number, extra: object = {}) {
    try {
      await api(`/api/submissions/${subId}/accept`, { body: extra });
      setDups(null); setErr(""); load(); onAccepted();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.duplicates) setDups({ sid: subId, list: e.detail.duplicates });
      else setErr(e.message);
    }
  }
  const state = (r: any) => (r.status === "ACTIVE" ? (r.submission ? r.submission.status : "WAITING") : r.status);

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted">Отправьте поставщику ссылку. Он откроет форму в браузере или на телефоне, впишет цены и условия, а вы увидите ответ здесь и добавите его в сравнение одной кнопкой.</p>
      {editable && (
        <form onSubmit={create} className="space-y-3 rounded-2xl border border-line p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-56 flex-1 text-sm"><span className="label-caps">Для какого поставщика (по желанию)</span>
              <input className="field mt-1" placeholder="Название компании" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
            <button className="btn-primary !min-h-12" disabled={!p.items.length}>+ Создать ссылку</button>
          </div>
          {!p.items.length && <p className="text-sm text-amber-700">Сначала добавьте товары на шаге «Сравнение» (кнопка «+ Добавить товар»).</p>}
          <details className="text-sm">
            <summary className="cursor-pointer font-semibold text-primary">Дополнительно: срок ссылки, НДС, сообщение</summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label><span className="label-caps">Ссылка действует</span>
                <select className="field mt-1" value={f.days} onChange={(e) => setF({ ...f, days: e.target.value })}>{[["3", "3 дня"], ["7", "7 дней"], ["14", "14 дней"], ["30", "30 дней"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
              <label><span className="label-caps">Ставка НДС по умолчанию, %</span><input inputMode="decimal" className="field mt-1" value={f.vat} onChange={(e) => setF({ ...f, vat: e.target.value })} /></label>
              <label className="sm:col-span-2"><span className="label-caps">Сообщение поставщику</span><textarea rows={2} className="field mt-1" placeholder="Например: цены нужны до пятницы, доставка до склада в Ташкенте" value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} /></label>
            </div>
          </details>
        </form>
      )}
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      {rows.length === 0 && <p className="text-sm text-muted">Ссылок пока нет.</p>}
      <ul className="space-y-3">
        {rows.map((r) => {
          const st = state(r), [label, cls] = STATUS[st] ?? [st, ""];
          const s = r.submission;
          return (
            <li key={r.id} className="rounded-2xl border border-line p-4">
              <div className="flex flex-wrap items-center gap-2">
                <b>{r.supplier_hint || "Без имени"}</b>
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{label}</span>
                <span className="ml-auto text-xs text-muted">до {new Date(r.expires_at).toLocaleDateString("ru-RU")}</span>
              </div>
              {r.status === "ACTIVE" && st !== "EXPIRED" && (
                <>
                  <ShareLink url={url(r.token)} who={r.supplier_hint || undefined} subject={`Запрос коммерческого предложения ${p.number}`}
                    text={`Здравствуйте! Просим направить коммерческое предложение по закупке ${p.number}. Заполните короткую форму по ссылке (2–3 минуты):`} />
                  {st === "WAITING" && <Reminder r={r} p={p} link={url(r.token)} />}
                  {editable && <button className="mt-2 text-sm font-semibold text-red-600 underline" onClick={() => confirm("Отозвать ссылку? Поставщик больше не сможет её открыть.") && run(() => api(`/api/invitations/${r.id}`, { method: "DELETE" }))}>Отозвать ссылку</button>}
                </>
              )}
              {s && (
                <div className="mt-3 rounded-xl bg-primary-soft/30 p-3 text-sm">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div><b>{s.payload.company}</b><span className="ml-2 text-muted">{[s.payload.phone, s.payload.email].filter(Boolean).join(" · ")}</span></div>
                    <div className="text-lg font-extrabold tabular-nums">{fmt(s.summary.total_with_vat)} <span className="text-xs font-medium text-muted">{p.currency}, с НДС</span></div>
                  </div>
                  <div className="mt-1 text-xs text-muted">
                    Цены по {s.summary.priced} из {s.summary.priced + s.summary.missing} позиций · срок {s.payload.delivery_days ?? "—"} дн. · {s.payload.payment_terms || "оплата не указана"} · версия {s.revision}
                  </div>
                  {s.summary.missing > 0 && <div className="mt-1 text-xs text-amber-600">Не по всем позициям есть цена — предложение будет неполным.</div>}
                  {s.summary.has_analogs && <div className="mt-1 text-xs text-amber-600">Поставщик предлагает аналог — потребуется техническая проверка.</div>}
                  {s.payload.comment && <div className="mt-1 text-xs">Комментарий: {s.payload.comment}</div>}
                  {s.status === "REJECTED" && s.decision_comment && <div className="mt-1 text-xs text-red-600">Причина отказа: {s.decision_comment}</div>}
                  {s.status === "NEW" && editable && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button className="btn-primary" onClick={() => accept(s.id)}>Добавить в сравнение</button>
                      <button className="btn" onClick={() => { const c = prompt("Причина отклонения"); if (c && c.trim().length >= 3) run(() => api(`/api/submissions/${s.id}/reject`, { body: { comment: c.trim() } })); }}>Отклонить</button>
                    </div>
                  )}
                  {dups && dups.sid === s.id && (
                    <div role="alert" className="mt-3 space-y-2 rounded-xl border border-amber-500 p-3">
                      <div>Возможно, такой поставщик уже есть в справочнике:</div>
                      {dups.list.map((d) => <button key={d.id} className="btn mr-2" onClick={() => accept(s.id, { supplier_id: d.id })}>Это «{d.name}» {d.inn ? `(ИНН ${d.inn})` : ""}</button>)}
                      <button className="btn" onClick={() => accept(s.id, { force_new: true })}>Нет, создать нового</button>
                    </div>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <p className="rounded-xl bg-[var(--warn-bg)] p-3 text-xs text-[var(--warn-text)]">Ссылка откроется у поставщика только если сервис доступен ему из интернета. Сейчас cp360.uz доступен лишь внутри локальной сети — для внешних поставщиков нужно опубликовать только адреса <code>/rfq/…</code> и <code>/api/public/…</code>.</p>
    </div>
  );
}
