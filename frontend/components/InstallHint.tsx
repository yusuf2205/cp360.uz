"use client";
import { useEffect, useState } from "react";

const KEY = "cp360-install-hint-off";

/** "Put cp360 on your phone's home screen". Shown on phones/tablets only, until installed or dismissed. */
export default function InstallHint() {
  const [ev, setEv] = useState<any>(null);
  const [kind, setKind] = useState<"" | "ios" | "other">("");
  const [off, setOff] = useState(true);

  useEffect(() => {
    try { if (localStorage.getItem(KEY)) return; } catch {}
    const standalone = window.matchMedia("(display-mode: standalone)").matches || (navigator as any).standalone;
    const ua = navigator.userAgent;
    const mobile = /Android|iPhone|iPad|iPod/i.test(ua) || (navigator.maxTouchPoints > 1 && /Macintosh/.test(ua));
    if (standalone || !mobile) return;
    setKind(/iPhone|iPad|iPod|Macintosh/i.test(ua) ? "ios" : "other");
    setOff(false);
    const h = (e: Event) => { e.preventDefault(); setEv(e); };
    window.addEventListener("beforeinstallprompt", h);
    return () => window.removeEventListener("beforeinstallprompt", h);
  }, []);

  if (off) return null;
  const close = () => { setOff(true); try { localStorage.setItem(KEY, "1"); } catch {} };
  return (
    <section className="card mb-6 flex flex-wrap items-center gap-4 border-2 border-primary/30 p-5" aria-label="Установка на телефон">
      <div className="grid size-14 shrink-0 place-items-center rounded-2xl bg-primary text-3xl font-extrabold text-white" aria-hidden>c</div>
      <div className="min-w-48 flex-1">
        <h2 className="text-lg font-bold">Поставьте cp360 на экран телефона</h2>
        {ev ? <p className="text-sm text-muted">Откроется как обычное приложение, без адресной строки.</p>
          : kind === "ios" ? <p className="text-sm text-muted">Нажмите кнопку «Поделиться» (квадрат со стрелкой) в Safari, затем «На экран «Домой»».</p>
          : <p className="text-sm text-muted">Откройте меню браузера (три точки) и выберите «Установить приложение» или «Добавить на главный экран».</p>}
      </div>
      {ev && <button className="btn-primary" onClick={async () => { ev.prompt(); try { await ev.userChoice; } catch {} setEv(null); close(); }}>Установить</button>}
      <button className="btn" onClick={close}>Не нужно</button>
    </section>
  );
}
