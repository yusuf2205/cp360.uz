"use client";
import PasswordCard from "@/components/PasswordCard";
import { useCallback, useEffect, useState } from "react";
import { QrDialog } from "@/components/ShareLink";
import { api } from "@/lib/api";

const ROLES: [string, string, string][] = [
  ["PROCUREMENT_MANAGER", "Снабженец", "Создаёт закупки, загружает предложения, сравнивает"],
  ["REVIEWER", "Проверяющий", "Проверяет сравнительные листы"],
  ["APPROVER", "Утверждающий", "Утверждает выбор поставщика"],
  ["VIEWER", "Только просмотр", "Видит документы, ничего не меняет"],
  ["ADMIN", "Администратор", "Управляет людьми и закупками"],
  ["SUPER_ADMIN", "Главный администратор", "Полный доступ ко всему"],
];
const roleName = (r: string) => ROLES.find((x) => x[0] === r)?.[1] ?? r;

function ago(iso?: string | null) {
  if (!iso) return "ещё не входил";
  const utc = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z"; // server times are UTC
  const m = Math.round((Date.now() - new Date(utc).getTime()) / 60000);
  if (m < 2) return "только что";
  if (m < 60) return `${m} мин. назад`;
  if (m < 60 * 24) return `${Math.round(m / 60)} ч. назад`;
  return new Date(utc).toLocaleDateString("ru-RU");
}

export default function Team() {
  const [users, setUsers] = useState<any[] | null>(null);
  const [sessions, setSessions] = useState<any[]>([]);
  const [me, setMe] = useState<any>(null);
  const [f, setF] = useState({ name: "", phone: "", role: "PROCUREMENT_MANAGER", department: "" });
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [qr, setQr] = useState(false);

  const load = useCallback(async () => {
    try {
      const [u, s, m] = await Promise.all([api("/api/users"), api("/api/auth/sessions"), api("/api/auth/me")]);
      setUsers(u); setSessions(s); setMe(m);
    } catch (e: any) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); const h = setInterval(load, 8000); return () => clearInterval(h); }, [load]);

  const run = (fn: () => Promise<any>, ok?: string) => fn().then(() => { setErr(""); setMsg(ok ?? ""); load(); }).catch((e) => { setMsg(""); setErr(e.message); });
  const pending = sessions.filter((s) => s.status === "PENDING");
  const siteUrl = typeof window !== "undefined" ? window.location.origin + "/login" : "";

  if (err && !users) return <p role="alert" className="text-red-600">{err}</p>;
  if (!users) return <div className="h-48 animate-pulse rounded-2xl bg-primary-soft/40" />;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">Сотрудники</h1>
          <p className="mt-1 text-muted">Кого вы добавите здесь по имени и телефону — тот сможет войти. Войти нужно один раз: устройство запомнит человека.</p>
        </div>
        <button className="btn" onClick={() => setQr(true)}>▦ QR-код для входа сотрудников</button>
      </header>
      {qr && <QrDialog url={siteUrl} title="Вход для сотрудников" hint="Сотрудник наводит камеру телефона, вводит своё имя и телефон — и работает. Подходит для офисной сети." onClose={() => setQr(false)} />}
      {me?.has_password && <PasswordCard />}
      {err && <p role="alert" className="rounded-xl border-2 border-red-300 bg-red-50 p-3 font-medium text-red-800">{err}</p>}
      {msg && <p role="status" className="rounded-xl bg-primary-soft p-3 font-medium">{msg}</p>}

      {pending.length > 0 && (
        <section className="card border-2 !border-amber-400 p-5" aria-label="Запросы на вход">
          <h2 className="mb-1 text-xl font-bold">Просят разрешить вход ({pending.length})</h2>
          <p className="mb-3 text-muted">Эти люди входят с нового устройства не из офиса. Разрешайте, только если вы их знаете.</p>
          <ul className="space-y-3">
            {pending.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-3 rounded-xl bg-primary-soft/40 p-3">
                <div className="min-w-0 flex-1"><div className="text-lg font-bold">{s.user}</div><div className="text-sm text-muted">{s.phone && `+${s.phone} · `}{s.device} · {s.ip}</div></div>
                <button className="btn-primary" onClick={() => run(() => api(`/api/auth/sessions/${s.id}/approve`, { method: "POST" }), `Вход разрешён: ${s.user}`)}>✓ Разрешить</button>
                <button className="btn" onClick={() => run(() => api(`/api/auth/sessions/${s.id}/deny`, { method: "POST" }), "Вход отклонён")}>Отклонить</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card p-5">
        <h2 className="mb-3 text-xl font-bold">Добавить сотрудника</h2>
        <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => { e.preventDefault(); run(() => api("/api/users", { body: { name: f.name.trim(), phone: f.phone, role: f.role, department: f.department || null } }).then(() => setF({ ...f, name: "", phone: "", department: "" })), `Добавлен: ${f.name}`); }}>
          <label><span className="label-caps">Имя и фамилия</span><input required minLength={2} className="field mt-1" placeholder="Азиз Каримов" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
          <label><span className="label-caps">Телефон</span><input required type="tel" inputMode="tel" className="field mt-1" placeholder="+998 90 123 45 67" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></label>
          <label><span className="label-caps">Кто это</span>
            <select className="field mt-1" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.filter((r) => r[0] !== "SUPER_ADMIN" || me?.role === "SUPER_ADMIN").map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <label><span className="label-caps">Подразделение (по желанию)</span><input className="field mt-1" placeholder="Закупки" value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} /></label>
          <div className="sm:col-span-2 lg:col-span-4"><button className="btn-primary">+ Добавить</button><span className="ml-3 text-sm text-muted">{ROLES.find((r) => r[0] === f.role)?.[2]}</span></div>
        </form>
      </section>

      <section className="space-y-3" aria-label="Список сотрудников">
        {users.map((u) => {
          const devs = sessions.filter((s) => s.user_id === u.id && s.status === "ACTIVE");
          const self = u.id === me?.id;
          return (
            <article key={u.id} className={`card p-4 ${u.active ? "" : "opacity-60"}`}>
              <div className="flex flex-wrap items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="text-lg font-bold">{u.name}{self && <span className="ml-2 rounded-full bg-primary-soft px-2 py-0.5 text-xs font-semibold text-primary">это вы</span>}{!u.active && <span className="ml-2 rounded-full bg-black/10 px-2 py-0.5 text-xs font-semibold">отключён</span>}</div>
                  <div className="text-sm text-muted">{u.phone ? `+${u.phone}` : "телефон не указан"}{u.department && ` · ${u.department}`} · {u.devices} устр. · был: {ago(u.last_seen)}</div>
                </div>
                <select aria-label={`Роль: ${u.name}`} className="field !w-auto" value={u.role} disabled={self} onChange={(e) => run(() => api(`/api/users/${u.id}`, { method: "PATCH", body: { role: e.target.value } }), "Роль изменена")}>
                  {ROLES.filter((r) => r[0] !== "SUPER_ADMIN" || me?.role === "SUPER_ADMIN" || u.role === "SUPER_ADMIN").map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
                <button className="btn" onClick={() => setOpen(open === u.id ? null : u.id)} aria-expanded={open === u.id}>Устройства ({devs.length})</button>
                {!self && (u.active
                  ? <button className="btn" onClick={() => confirm(`Отключить доступ: ${u.name}? Все его устройства сразу выйдут из системы.`) && run(() => api(`/api/users/${u.id}`, { method: "PATCH", body: { active: false } }), "Доступ отключён")}>Отключить</button>
                  : <button className="btn-primary" onClick={() => run(() => api(`/api/users/${u.id}`, { method: "PATCH", body: { active: true } }), "Доступ включён")}>Включить</button>)}
              </div>
              {open === u.id && (
                <div className="mt-3 space-y-2 border-t border-line pt-3">
                  <PhoneEditor user={u} run={run} />
                  {devs.length === 0 ? <p className="text-sm text-muted">Нет активных устройств.</p> : devs.map((d) => (
                    <div key={d.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-primary-soft/30 p-3 text-sm">
                      <span><b>{d.device}</b> · был: {ago(d.last_seen)} · {d.ip}</span>
                      <button className="font-semibold text-red-600 underline" onClick={() => run(() => api(`/api/auth/sessions/${d.id}/revoke`, { method: "POST" }), "Устройство вышло из системы")}>Выйти с устройства</button>
                    </div>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </section>
    </div>
  );
}

function PhoneEditor({ user, run }: { user: any; run: (fn: () => Promise<any>, ok?: string) => void }) {
  const [name, setName] = useState(user.name);
  const [phone, setPhone] = useState(user.phone ? `+${user.phone}` : "");
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); run(() => api(`/api/users/${user.id}`, { method: "PATCH", body: { name, phone } }), "Сохранено"); }}>
      <label className="text-sm"><span className="label-caps">Имя</span><input className="field mt-1" value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label className="text-sm"><span className="label-caps">Телефон</span><input className="field mt-1" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
      <button className="btn">Сохранить</button>
    </form>
  );
}
