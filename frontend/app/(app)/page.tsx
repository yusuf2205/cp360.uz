"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fmt } from "@/lib/api";

const CARDS: [string, string, string | null][] = [
  ["total", "Всего закупок", ""],
  ["active", "Активные", ""],
  ["draft", "Черновики", "DRAFT"],
  ["in_review", "На проверке", "IN_REVIEW"],
  ["in_approval", "На согласовании", "IN_APPROVAL"],
  ["approved", "Утверждённые", "APPROVED"],
  ["rejected", "Отклонённые", "REJECTED"],
  ["insufficient_offers", "Меньше 3 предложений", null],
];

export default function Dashboard() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api("/api/dashboard").then(setD).catch((e) => setErr(e.message)); }, []);
  if (err) return <p role="alert" className="text-red-600">{err}</p>;
  if (!d) return <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-20 animate-pulse rounded-lg bg-black/5 dark:bg-white/10" />)}</div>;
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Панель</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {CARDS.map(([k, label, status]) => (
          <Link key={k} href={status ? `/procurements?status=${status}` : "/procurements"} className="card p-4 hover:border-blue-500">
            <div className="text-2xl font-semibold">{d[k]}</div>
            <div className="text-sm opacity-70">{label}</div>
          </Link>
        ))}
      </div>
      <section className="card p-4">
        <h2 className="font-medium mb-2">Сумма утверждённых закупок</h2>
        {Object.keys(d.approved_amount_by_currency).length === 0 ? <p className="text-sm opacity-60">Нет утверждённых закупок</p> :
          Object.entries(d.approved_amount_by_currency).map(([c, v]) => <div key={c}>{fmt(v as string)} {c}</div>)}
        <p className="mt-2 text-xs opacity-60">Экономия не показывается: для неё нужна явно заданная база сравнения.</p>
      </section>
      {d.recent.length > 0 && (
        <section>
          <h2 className="font-medium mb-2">Последние действия</h2>
          <ul className="text-sm space-y-1">{d.recent.map((a: any, i: number) => <li key={i}>{new Date(a.at).toLocaleString("ru-RU")} — {a.action} {a.entity ?? ""} {a.entity_id ?? ""}</li>)}</ul>
        </section>
      )}
    </div>
  );
}
