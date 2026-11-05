"use client";
import { useEffect, useState } from "react";
import { api, STATUS_RU } from "@/lib/api";

const NEXT: Record<string, [string, string, boolean][]> = {
  DRAFT: [["PREPARED", "Подготовлено", false]], RETURNED: [["PREPARED", "Подготовлено", false]],
  PREPARED: [["IN_REVIEW", "Отправить на проверку", false]],
  IN_REVIEW: [["IN_APPROVAL", "Передать на согласование", false], ["RETURNED", "Вернуть на доработку", false]],
  IN_APPROVAL: [["APPROVED", "Утвердить", true], ["RETURNED", "Вернуть на доработку", false], ["REJECTED", "Отклонить", true]],
};

export default function WorkflowPanel({ p, reload }: { p: any; reload: () => void }) {
  const [hist, setHist] = useState<any[]>([]);
  const [comment, setComment] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { api(`/api/procurements/${p.id}/history`).then(setHist); }, [p.id, p.status]);
  async function go(to: string, needConfirm: boolean) {
    if (needConfirm && !confirm(`Подтвердите: ${STATUS_RU[to]}. Это не является квалифицированной электронной подписью.`)) return;
    try { await api(`/api/procurements/${p.id}/transition`, { body: { to, comment: comment || null, confirm: needConfirm } }); setComment(""); setErr(""); reload(); }
    catch (e: any) { setErr(e.message); }
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input aria-label="Комментарий" placeholder="Комментарий" className="field min-w-48 flex-1" value={comment} onChange={(e) => setComment(e.target.value)} />
        {(NEXT[p.status] ?? []).map(([to, label, c]) => <button key={to} onClick={() => go(to, c)} className="btn">{label}</button>)}
        {["APPROVED", "REJECTED"].includes(p.status) && <button className="btn" onClick={() => confirm("Создать новую версию документа?") && api(`/api/procurements/${p.id}/new-version?confirm=true`, { method: "POST" }).then(reload).catch((e) => setErr(e.message))}>Новая версия</button>}
      </div>
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      <ol className="space-y-1 text-sm">{hist.map((h, i) => <li key={i}>{new Date(h.at).toLocaleString("ru-RU")} — {STATUS_RU[h.from]} → <b>{STATUS_RU[h.to]}</b>{h.comment && ` («${h.comment}»)`}</li>)}</ol>
      {hist.length === 0 && <p className="text-sm text-muted">История согласования пуста</p>}
    </div>
  );
}
