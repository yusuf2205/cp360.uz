"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

const STEPS = [
  { href: "/import", label: "1. Загрузка" },
  { href: "/compare", label: "2. Сравнение" },
  { href: "/export", label: "3. Excel" },
];

export function PageHead({ step, title, subtitle, right, help }: { step: number; title: string; subtitle?: React.ReactNode; right?: React.ReactNode; help?: string }) {
  return (
    <header className="mb-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="label-caps">Шаг {step} из 3</div>
          <h1 className="mt-1 text-3xl font-extrabold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        </div>
        {right}
      </div>
      <nav className="mt-5 flex flex-wrap gap-2" aria-label="Шаги">
        {STEPS.map((s, i) => (
          <Link key={s.href} href={s.href} className={i + 1 === step ? "pill-active" : "pill"}>{s.label}</Link>
        ))}
      </nav>
      {help && <p className="mt-4 flex gap-3 rounded-xl bg-primary-soft p-4 text-base leading-relaxed"><span aria-hidden>💡</span><span>{help}</span></p>}
    </header>
  );
}

/** Procurement picker shown above each step: choose the active one or start a new one. */
export function ActiveBar({ pid, onPick }: { pid: number | null; onPick: (id: number) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const router = useRouter();
  useEffect(() => { api("/api/procurements?limit=200").then(setRows).catch(() => {}); }, [pid]);
  async function create() {
    const purpose = window.prompt("Назначение закупки (например: Металлопрокат для цеха №2)");
    if (purpose === null) return;
    const p = await api("/api/procurements", { body: { purpose, currency: "UZS" } });
    onPick(p.id);
    router.push("/import");
  }
  return (
    <div className="mb-5 flex flex-wrap items-center gap-2 text-sm">
      <span className="font-semibold">Закупка:</span>
      <select aria-label="Активная закупка" className="field !w-auto min-w-64" value={pid ?? ""} onChange={(e) => e.target.value && onPick(Number(e.target.value))}>
        <option value="">— выберите закупку —</option>
        {rows.map((r) => <option key={r.id} value={r.id}>{r.number} · {r.purpose || "без названия"}</option>)}
      </select>
      <button className="btn" onClick={create}>+ Новая закупка</button>
      {pid && <Link className="text-primary underline" href={`/procurements/${pid}`}>Параметры</Link>}
    </div>
  );
}

export function NoActive({ onPick }: { onPick: (id: number) => void }) {
  return (
    <div className="card p-10 text-center">
      <p className="mb-4 text-muted">Выберите закупку или создайте новую, чтобы начать.</p>
      <ActiveBar pid={null} onPick={onPick} />
    </div>
  );
}
