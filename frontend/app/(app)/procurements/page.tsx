"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, STATUS_RU } from "@/lib/api";

function List() {
  const sp = useSearchParams();
  const router = useRouter();
  const [rows, setRows] = useState<any[] | null>(null);
  const [q, setQ] = useState("");
  const status = sp.get("status") ?? "";
  const [err, setErr] = useState("");

  useEffect(() => {
    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    if (q) qs.set("q", q);
    const h = setTimeout(() => api(`/api/procurements?${qs}`).then(setRows).catch((e) => setErr(e.message)), 200);
    return () => clearTimeout(h);
  }, [status, q]);

  async function create() {
    try {
      const p = await api("/api/procurements", { body: { purpose: "", currency: "UZS" } });
      localStorage.setItem("cp_active", String(p.id)); router.push("/import");
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold mr-auto">Закупки</h1>
        <input aria-label="Поиск" placeholder="Поиск по номеру или назначению" value={q} onChange={(e) => setQ(e.target.value)} className="rounded border border-black/20 dark:border-white/20 bg-transparent px-3 py-1.5 text-sm w-64" />
        <select aria-label="Статус" value={status} onChange={(e) => router.push(e.target.value ? `?status=${e.target.value}` : "?")} className="rounded border border-black/20 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm">
          <option value="">Все статусы</option>
          {["DRAFT", "PREPARED", "IN_REVIEW", "IN_APPROVAL", "APPROVED", "RETURNED", "REJECTED"].map((s) => <option key={s} value={s}>{STATUS_RU[s]}</option>)}
        </select>
        <button onClick={create} className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white">+ Новая закупка</button>
      </div>
      {err && <p role="alert" className="text-red-600 text-sm">{err}</p>}
      {!rows ? <div className="h-32 animate-pulse rounded bg-black/5 dark:bg-white/10" /> : rows.length === 0 ? <p className="text-sm opacity-60">Закупок нет</p> : (
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="text-left border-b border-black/10 dark:border-white/15"><th className="py-2 pr-3">Номер</th><th className="pr-3">Назначение</th><th className="pr-3">Подразделение</th><th className="pr-3">Статус</th><th>Создана</th></tr></thead>
          <tbody>{rows.map((p) => (
            <tr key={p.id} className="border-b border-black/5 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5">
              <td className="py-2 pr-3"><Link className="text-blue-600 underline" href={`/compare?p=${p.id}`}>{p.number}</Link></td>
              <td className="pr-3">{p.purpose || "—"}</td><td className="pr-3">{p.department || "—"}</td>
              <td className="pr-3">{STATUS_RU[p.status]}</td><td>{new Date(p.created_at).toLocaleDateString("ru-RU")}</td>
            </tr>))}</tbody>
        </table></div>
      )}
    </div>
  );
}

export default function Page() { return <Suspense><List /></Suspense>; }
