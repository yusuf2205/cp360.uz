"use client";
import { useState } from "react";
import { api } from "@/lib/api";

/** Change own password. Only shown to accounts that have one (administrators). */
export default function PasswordCard() {
  const [f, setF] = useState({ current: "", next: "", again: "" });
  const [show, setShow] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (f.next.length < 10) return setMsg({ ok: false, text: "Новый пароль слишком короткий: нужно не меньше 10 символов." });
    if (f.next !== f.again) return setMsg({ ok: false, text: "Новый пароль и его повтор не совпадают." });
    setBusy(true);
    try {
      await api("/api/auth/change-password", { body: { current: f.current, new: f.next } });
      setF({ current: "", next: "", again: "" });
      setMsg({ ok: true, text: "Пароль изменён. На других устройствах этот администратор вышел из системы." });
    } catch (e: any) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  }
  const t = show ? "text" : "password";
  return (
    <details className="card p-5">
      <summary className="cursor-pointer text-lg font-bold">Сменить мой пароль</summary>
      <form onSubmit={submit} className="mt-4 grid max-w-md gap-3">
        <label><span className="label-caps">Текущий пароль</span><input className="field mt-1" type={t} autoComplete="current-password" required value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} /></label>
        <label><span className="label-caps">Новый пароль (от 10 символов)</span><input className="field mt-1" type={t} autoComplete="new-password" required minLength={10} value={f.next} onChange={(e) => setF({ ...f, next: e.target.value })} /></label>
        <label><span className="label-caps">Новый пароль ещё раз</span><input className="field mt-1" type={t} autoComplete="new-password" required value={f.again} onChange={(e) => setF({ ...f, again: e.target.value })} /></label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Показать пароли</label>
        {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "rounded-xl bg-primary-soft p-3" : "rounded-xl border-2 border-red-300 bg-red-50 p-3 text-red-800"}>{msg.text}</p>}
        <button className="btn-primary" disabled={busy}>{busy ? "Сохраняю…" : "Сменить пароль"}</button>
      </form>
    </details>
  );
}
