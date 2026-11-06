"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import SizeControl from "@/components/SizeControl";
import { api, token } from "@/lib/api";

const MAIN = [
  { href: "/", label: "Обзор", hint: "Что сейчас происходит", icon: "⌂" },
  { href: "/import", label: "Умный импорт", hint: "Добавить предложения", icon: "✦" },
  { href: "/compare", label: "Сравнение", hint: "Сравнить цены", icon: "▥" },
  { href: "/export", label: "Экспорт Excel", hint: "Скачать готовый лист", icon: "▤" },
];
const REF = [
  { href: "/procurements", label: "Все закупки", hint: "Список и поиск", icon: "☰" },
  { href: "/suppliers", label: "Поставщики", hint: "Справочник компаний", icon: "⚑" },
  { href: "/history", label: "История цен", hint: "Сколько платили раньше", icon: "◷" },
];
const TEAM = { href: "/team", label: "Сотрудники", hint: "Кто может входить", icon: "☺" };

function HelpDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const steps: [string, string][] = [
    ["Добавьте предложения", "Поставщик прислал цены? Загрузите его файл или фото, вставьте текст письма, впишите цены сами — или отправьте поставщику ссылку, и он заполнит форму на телефоне."],
    ["Сравните цены", "Все предложения окажутся в одной таблице. Самая низкая цена по каждому товару отмечена зелёным и звёздочкой. Прочерк «—» значит: у поставщика этого товара нет."],
    ["Скачайте Excel", "Нажмите «Скачать Excel» — получите готовый сравнительный лист для печати и подписи."],
  ];
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="help-title" onClick={onClose}>
      <div className="card max-h-[90vh] w-full max-w-xl overflow-auto p-6" onClick={(e) => e.stopPropagation()}>
        <h2 id="help-title" className="mb-4 text-2xl font-extrabold">Как это работает</h2>
        <ol className="space-y-4">
          {steps.map(([t, d], i) => (
            <li key={t} className="flex gap-4">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary text-lg font-extrabold text-white" aria-hidden>{i + 1}</span>
              <div><div className="text-lg font-bold">{t}</div><p className="text-muted">{d}</p></div>
            </li>
          ))}
        </ol>
        <p className="mt-5 rounded-xl bg-primary-soft p-3 text-sm">Программа ничего не придумывает: всё, что она распознала, вы проверяете сами перед добавлением. Если что-то непонятно — нажмите «Назад» или закройте это окно, ничего не сломается.</p>
        <button autoFocus className="btn-primary mt-5 w-full" onClick={onClose}>Понятно</button>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [open, setOpen] = useState(false);
  const [help, setHelp] = useState(false);
  const [loadErr, setLoadErr] = useState("");

  useEffect(() => {
    if (!token.get()) return void router.replace("/login");
    api("/api/auth/me").then(setMe).catch((e) => setLoadErr(e?.message || "Нет связи с сервером"));
  }, [router]);

  if (loadErr) return (
    <div className="space-y-4 p-8" role="alert">
      <p className="text-lg font-semibold text-red-600">Не удалось загрузить данные</p>
      <p className="text-muted">{loadErr}</p>
      <div className="flex gap-3"><button className="btn-primary" onClick={() => location.reload()}>Попробовать ещё раз</button><button className="btn" onClick={() => { token.clear(); location.href = "/login"; }}>Войти заново</button></div>
    </div>
  );
  if (!me) return <div className="p-8 text-lg text-muted" aria-busy="true">Загрузка…</div>;

  const link = (n: { href: string; label: string; hint: string; icon: string }) => {
    const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
    return (
      <Link key={n.href} href={n.href} onClick={() => setOpen(false)} aria-current={active ? "page" : undefined}
        className={`flex items-center gap-3 rounded-xl px-4 py-3 ${active ? "bg-primary-soft text-primary" : "hover:bg-primary-soft/60"}`}>
        <span className="w-6 text-center text-lg" aria-hidden>{n.icon}</span>
        <span><span className={`block text-base font-semibold leading-tight ${active ? "" : "text-foreground"}`}>{n.label}</span><span className="block text-sm font-normal text-muted">{n.hint}</span></span>
      </Link>
    );
  };

  return (
    <div className="min-h-screen md:flex">
      <header className="flex items-center justify-between border-b border-line bg-card px-4 py-3 md:hidden">
        <b className="text-lg">cp360.uz</b>
        <button aria-label={open ? "Закрыть меню" : "Открыть меню"} aria-expanded={open} onClick={() => setOpen(!open)} className="btn !px-4">{open ? "✕ Закрыть" : "☰ Меню"}</button>
      </header>
      <aside className={`${open ? "flex" : "hidden"} w-full shrink-0 flex-col border-r border-line bg-card p-4 md:sticky md:top-0 md:flex md:h-screen md:w-80 md:overflow-auto`} aria-label="Основное меню">
        <div className="mb-6 hidden items-center gap-3 px-2 pt-2 md:flex">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary text-xl font-extrabold text-white" aria-hidden>C</div>
          <div><div className="text-xl font-extrabold leading-tight">cp360.uz</div><div className="text-xs font-semibold tracking-wide text-muted">УМНЫЕ ЗАКУПКИ</div></div>
        </div>
        <nav className="space-y-1">{MAIN.map(link)}</nav>
        <div className="label-caps mb-1 mt-5 px-4">Справочники</div>
        <nav className="space-y-1">{(["SUPER_ADMIN", "ADMIN"].includes(me.role) ? [...REF, TEAM] : REF).map(link)}</nav>
        <div className="mt-auto space-y-4 pt-6">
          <button className="btn w-full" onClick={() => { setHelp(true); setOpen(false); }}>❓ Как это работает?</button>
          <SizeControl />
          <div className="px-1 text-sm">
            <div className="font-semibold">{me.name}</div>
            <div className="text-muted">{({ SUPER_ADMIN: "Главный администратор", ADMIN: "Администратор", PROCUREMENT_MANAGER: "Снабженец", REVIEWER: "Проверяющий", APPROVER: "Утверждающий", VIEWER: "Только просмотр" } as Record<string, string>)[me.role] ?? me.role}</div>
            <button className="mt-2 font-semibold text-primary underline" onClick={async () => { try { await api("/api/auth/logout", { method: "POST" }); } catch {} token.clear(); router.replace("/login"); }}>Выйти</button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">{children}</main>
      {help && <HelpDialog onClose={() => setHelp(false)} />}
    </div>
  );
}
