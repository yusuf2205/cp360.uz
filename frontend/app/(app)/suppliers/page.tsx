"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function Suppliers() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [form, setForm] = useState({ name: "", inn: "", phone: "", email: "" });
  const [err, setErr] = useState("");
  const [dups, setDups] = useState<any[]>([]);
  const load = () => api("/api/suppliers").then(setRows).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  async function add(force = false) {
    setErr(""); setDups([]);
    try {
      await api(`/api/suppliers${force ? "?force=true" : ""}`, { body: { name: form.name, inn: form.inn || null, contacts: { phone: form.phone, email: form.email } } });
      setForm({ name: "", inn: "", phone: "", email: "" });
      load();
    } catch (e: any) {
      if (e.status === 409) setDups(e.detail.duplicates);
      else setErr(e.message);
    }
  }
  const inp = "rounded border border-black/20 dark:border-white/20 bg-transparent px-3 py-1.5 text-sm";
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Поставщики</h1>
      <form onSubmit={(e) => { e.preventDefault(); add(); }} className="flex flex-wrap gap-2">
        <input required placeholder="Название" className={inp} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input placeholder="ИНН" className={inp} value={form.inn} onChange={(e) => setForm({ ...form, inn: e.target.value })} />
        <input placeholder="Телефон" className={inp} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        <input placeholder="Email" className={inp} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <button className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white">Добавить</button>
      </form>
      {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
      {dups.length > 0 && (
        <div role="alert" className="rounded border border-amber-500 p-3 text-sm">
          Возможный дубль: {dups.map((d) => `${d.name} (${d.inn ?? "без ИНН"})`).join("; ")}
          <button className="ml-3 underline" onClick={() => add(true)}>Всё равно создать</button>
        </div>
      )}
      {!rows ? <div className="h-24 animate-pulse rounded bg-black/5 dark:bg-white/10" /> : (
        <table className="w-full text-sm"><thead><tr className="text-left border-b border-black/10 dark:border-white/15"><th className="py-2">Название</th><th>ИНН</th><th>Контакты</th></tr></thead>
          <tbody>{rows.map((s) => <tr key={s.id} className="border-b border-black/5 dark:border-white/10"><td className="py-2">{s.name}</td><td>{s.inn ?? "—"}</td><td>{[s.contacts?.phone, s.contacts?.email].filter(Boolean).join(", ") || "—"}</td></tr>)}</tbody></table>
      )}
    </div>
  );
}
