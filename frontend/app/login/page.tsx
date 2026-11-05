"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import SizeControl from "@/components/SizeControl";
import { api, token } from "@/lib/api";

/** "901234567" -> "90 123 45 67", "998901234567" -> "+998 90 123 45 67" while typing. */
function formatPhone(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 12);
  const local = d.startsWith("998") ? d.slice(3) : d;
  const g = [local.slice(0, 2), local.slice(2, 5), local.slice(5, 7), local.slice(7, 9)].filter(Boolean).join(" ");
  return d.startsWith("998") ? `+998${g ? " " + g : ""}` : g;
}

export default function Login() {
  const r = useRouter();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{ id: number; secret: string } | null>(null);
  const [denied, setDenied] = useState(false);
  const [admin, setAdmin] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  // already signed in on this device: go straight in (that is the whole point of "sign in once")
  useEffect(() => {
    if (token.get()) r.replace("/");
    try {
      setName(localStorage.getItem("cp_name") ?? "");
      setPhone(localStorage.getItem("cp_phone") ?? "");
      const p = JSON.parse(localStorage.getItem("cp_pending") ?? "null");
      if (p) setPending(p);
    } catch {}
  }, [r]);

  useEffect(() => {
    if (!pending) return;
    const tick = async () => {
      try {
        const s = await api(`/api/auth/device-status?session_id=${pending.id}&secret=${encodeURIComponent(pending.secret)}`);
        if (s.status === "ACTIVE") { token.set(s.access_token); localStorage.removeItem("cp_pending"); r.replace("/"); }
        else if (s.status !== "PENDING") { localStorage.removeItem("cp_pending"); setPending(null); setDenied(true); }
      } catch { /* keep waiting: the network may blink */ }
    };
    tick();
    timer.current = setInterval(tick, 3000);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [pending, r]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(""); setDenied(false);
    try {
      const res = await api("/api/auth/phone-login", { body: { name: name.trim(), phone } });
      try { localStorage.setItem("cp_name", name.trim()); localStorage.setItem("cp_phone", phone); } catch {}
      if (res.pending) {
        const p = { id: res.session_id, secret: res.poll_secret };
        localStorage.setItem("cp_pending", JSON.stringify(p));
        setPending(p);
      } else { token.set(res.access_token); r.replace("/"); }
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  async function passwordLogin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const res = await api("/api/auth/login", { body: { email: email.trim(), password } });
      token.set(res.access_token); r.replace("/");
    } catch (e: any) {
      setErr(e.status === 401 ? "Неверная почта или пароль." : e.message);
    } finally { setBusy(false); }
  }

  const Logo = (
    <div className="flex items-center gap-3">
      <div className="grid h-14 w-14 place-items-center rounded-xl bg-primary text-2xl font-extrabold text-white" aria-hidden>C</div>
      <div><h1 className="text-2xl font-extrabold leading-tight">cp360.uz</h1><p className="text-muted">Умные закупки</p></div>
    </div>
  );

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <div className="w-full max-w-md space-y-4">
        {pending ? (
          <div className="card space-y-4 p-6 text-center sm:p-8" role="status" aria-live="polite">
            {Logo}
            <div className="mx-auto grid h-16 w-16 animate-pulse place-items-center rounded-full bg-primary-soft text-3xl" aria-hidden>⏳</div>
            <p className="text-xl font-bold">Ждём подтверждения администратора</p>
            <p className="text-muted">Вы входите с нового устройства не из офиса. Администратору отправлен запрос — как только он разрешит, вход произойдёт сам. Страницу можно не закрывать.</p>
            <button className="btn w-full" onClick={() => { localStorage.removeItem("cp_pending"); setPending(null); }}>Отменить</button>
          </div>
        ) : admin ? (
          <form onSubmit={passwordLogin} className="card space-y-5 p-6 sm:p-8">
            {Logo}
            <p className="text-lg font-semibold">Вход администратора по паролю</p>
            <label className="block"><span className="mb-1.5 block font-semibold">Электронная почта</span>
              <input className="field" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            <label className="block"><span className="mb-1.5 block font-semibold">Пароль</span>
              <div className="flex gap-2">
                <input className="field" type={show ? "text" : "password"} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
                <button type="button" className="btn shrink-0" aria-pressed={show} onClick={() => setShow(!show)}>{show ? "Скрыть" : "Показать"}</button>
              </div></label>
            {err && <p role="alert" className="rounded-xl border-2 border-red-300 bg-red-50 p-3 font-medium text-red-800 dark:bg-red-950 dark:text-red-200">{err}</p>}
            <button disabled={busy} className="btn-primary w-full !min-h-14 !text-lg">{busy ? "Входим…" : "Войти"}</button>
            <button type="button" className="w-full text-center font-semibold text-primary underline" onClick={() => { setAdmin(false); setErr(""); }}>← Вход по имени и телефону</button>
          </form>
        ) : (
          <form onSubmit={submit} className="card space-y-5 p-6 sm:p-8">
            {Logo}
            <p className="text-lg font-semibold">Войдите — это нужно один раз</p>
            <label className="block"><span className="mb-1.5 block font-semibold">Ваше имя</span>
              <input className="field !min-h-14 !text-lg" autoComplete="name" autoFocus required minLength={2} placeholder="Например: Азиз" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="block"><span className="mb-1.5 block font-semibold">Номер телефона</span>
              <input className="field !min-h-14 !text-lg" type="tel" inputMode="tel" autoComplete="tel" required placeholder="+998 90 123 45 67" value={phone} onChange={(e) => setPhone(formatPhone(e.target.value))} /></label>
            {err && <p role="alert" className="rounded-xl border-2 border-red-300 bg-red-50 p-3 font-medium text-red-800 dark:bg-red-950 dark:text-red-200">{err}</p>}
            {denied && <p role="alert" className="rounded-xl border-2 border-red-300 bg-red-50 p-3 font-medium text-red-800 dark:bg-red-950 dark:text-red-200">Администратор не разрешил вход с этого устройства.</p>}
            <button disabled={busy} className="btn-primary w-full !min-h-14 !text-lg">{busy ? "Входим…" : "Войти"}</button>
            <p className="text-sm text-muted">Следующий раз пароль и вход не понадобятся: устройство запомнит вас. Нет доступа? Попросите администратора добавить ваше имя и телефон.</p>
            <button type="button" className="w-full text-center text-sm font-semibold text-primary underline" onClick={() => { setAdmin(true); setErr(""); }}>Вход администратора по паролю</button>
          </form>
        )}
        <div className="flex justify-center"><SizeControl /></div>
      </div>
    </main>
  );
}
