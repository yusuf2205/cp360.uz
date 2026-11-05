"use client";
import { useEffect, useMemo, useState } from "react";
import { downloadQrPng, qrSvg } from "@/lib/qr";

type Props = { url: string; subject: string; text: string; who?: string };

/** Every way a buyer might hand a link to a supplier, one tap each. */
export default function ShareLink({ url, subject, text, who }: Props) {
  const [qr, setQr] = useState(false);
  const [copied, setCopied] = useState(false);
  const [canShare, setCanShare] = useState(false);
  useEffect(() => { setCanShare(typeof navigator !== "undefined" && !!(navigator as any).share); }, []);

  const body = `${text}\n${url}`;
  const enc = encodeURIComponent;
  const links = [
    { label: "Telegram", icon: "✈", href: `https://t.me/share/url?url=${enc(url)}&text=${enc(text)}` },
    { label: "WhatsApp", icon: "💬", href: `https://wa.me/?text=${enc(body)}` },
    { label: "Почта", icon: "✉", href: `mailto:?subject=${enc(subject)}&body=${enc(body)}` },
    { label: "SMS", icon: "📱", href: `sms:?&body=${enc(body)}` },
  ];

  async function copy() {
    try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1800); }
    catch { window.prompt("Скопируйте ссылку:", url); }
  }

  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input readOnly aria-label="Ссылка для поставщика" className="field min-w-0 flex-1 text-sm" value={url} onFocus={(e) => e.target.select()} />
        <button type="button" className="btn" onClick={copy}>{copied ? "Скопировано ✓" : "Копировать"}</button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <button type="button" className="btn-primary col-span-2 !min-h-14 !text-lg" onClick={() => setQr(true)}>▦ Показать QR-код</button>
        {links.map((l) => <a key={l.label} className="btn whitespace-nowrap" target="_blank" rel="noreferrer" href={l.href}><span aria-hidden>{l.icon}</span> {l.label}</a>)}
        {canShare && <button type="button" className="btn col-span-2" onClick={() => (navigator as any).share({ title: subject, text, url }).catch(() => {})}>Поделиться другим способом…</button>}
      </div>
      {qr && <QrDialog url={url} who={who} onClose={() => setQr(false)} />}
    </div>
  );
}

export function QrDialog({ url, who, onClose, title = "Сканируйте камерой телефона", hint }: { url: string; who?: string; onClose: () => void; title?: string; hint?: string }) {
  const svg = useMemo(() => qrSvg(url), [url]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-labelledby="qr-title" onClick={onClose}>
      <div id="qr-print" className="card w-full max-w-md space-y-4 p-6 text-center" onClick={(e) => e.stopPropagation()}>
        <h2 id="qr-title" className="text-2xl font-extrabold">{title}</h2>
        {who && <p className="text-lg font-semibold">{who}</p>}
        <div className="mx-auto w-full max-w-xs overflow-hidden rounded-xl border-2 border-line bg-white" dangerouslySetInnerHTML={{ __html: svg }} />
        <p className="text-muted">{hint ?? "Откройте камеру телефона и наведите на код — откроется форма коммерческого предложения."}</p>
        <p className="break-all text-xs text-muted">{url}</p>
        <div className="no-print grid gap-2 sm:grid-cols-2">
          <button className="btn" onClick={() => downloadQrPng(svg, "qr-cp360.png")}>⬇ Скачать картинку</button>
          <button className="btn" onClick={() => window.print()}>🖨 Распечатать</button>
          <button autoFocus className="btn-primary sm:col-span-2" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}
