"use client";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import SizeControl from "@/components/SizeControl";
import { mulM, showMicro, toMicro, totals } from "@/lib/dec";
import { Lang, tr } from "@/lib/rfq-i18n";

const ORANGE = "#ff6a13";
const MUTED = "#aab2c8";
const inp = "w-full min-h-[3.25rem] rounded-xl border-2 border-white/15 bg-[#1a1e2b] px-4 py-3 text-[1.05rem] text-[#f2f4fa] outline-none placeholder:text-[#7d86a0] focus:border-[#ff6a13]";
const card = "rounded-2xl border border-white/10 bg-[#12151f] p-5 sm:p-7";
const lbl = "mb-2 block text-[1.02rem] font-semibold text-[#d5d9e8]";

type Line = { price: string; altOpen: boolean; alt: string; note: string };

async function call(path: string, body?: unknown) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let d = data.detail ?? res.statusText;
    if (Array.isArray(d)) d = d.map((x: any) => x.msg).join("; ");
    throw Object.assign(new Error(typeof d === "string" ? d : "Ошибка"), { status: res.status });
  }
  return data;
}

function Step({ n, title, id, lang, children }: { n: number; title: string; id: string; lang: Lang; children: React.ReactNode }) {
  return (
    <section id={id} className={`${card} scroll-mt-24`} aria-labelledby={id + "-h"}>
      <div className="mb-5 flex items-center gap-4">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full text-xl font-extrabold text-white" style={{ background: ORANGE }} aria-hidden>{n}</div>
        <h2 id={id + "-h"} className="text-[1.35rem] font-bold leading-tight"><span className="sr-only">{tr(lang, "step")} {n}. </span>{title}</h2>
      </div>
      {children}
    </section>
  );
}

export default function SupplierForm() {
  const { token } = useParams<{ token: string }>();
  const [lang, setLang] = useState<Lang>("ru");
  const [info, setInfo] = useState<any>(null);
  const [fatal, setFatal] = useState("");
  const [errs, setErrs] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const errRef = useRef<HTMLDivElement>(null);
  const [f, setF] = useState({ company: "", inn: "", contact_person: "", phone: "", email: "", vatIncl: true, vatRate: "12", validDays: "7", deliveryDays: "", deliveryTerms: "Доставка поставщиком", deliveryCost: "", payKind: "Постоплата", payDays: "", payOther: "", warranty: "", comment: "" });
  const [lines, setLines] = useState<Record<number, Line>>({});
  const t = (k: string, v?: Record<string, string | number>) => tr(lang, k, v);

  useEffect(() => {
    try { const saved = localStorage.getItem("cp_lang"); setLang(saved === "uz" || saved === "ru" ? saved : navigator.language?.toLowerCase().startsWith("uz") ? "uz" : "ru"); } catch {}
  }, []);
  const chooseLang = (l: Lang) => { setLang(l); try { localStorage.setItem("cp_lang", l); } catch {} };

  useEffect(() => {
    call(`/api/public/rfq/${token}`).then((d) => {
      setInfo(d);
      const init: Record<number, Line> = {};
      d.items.forEach((i: any) => (init[i.id] = { price: "", altOpen: false, alt: "", note: "" }));
      const sub = d.submission?.payload;
      setF((x) => ({ ...x, company: d.supplier_hint ?? "", vatRate: d.vat_rate_default ?? "12" }));
      if (sub) {
        sub.lines.forEach((l: any) => (init[l.item_id] = { price: l.unit_price ?? "", altOpen: !!l.alt_name, alt: l.alt_name ?? "", note: l.note ?? "" }));
        const pay = sub.payment_terms ?? "";
        const m = pay.match(/^Постоплата (\d+) дн/);
        setF((x) => ({ ...x, company: sub.company, inn: sub.inn ?? "", contact_person: sub.contact_person ?? "", phone: sub.phone ?? "", email: sub.email ?? "", vatIncl: sub.prices_include_vat,
          vatRate: sub.vat_rate != null ? String(sub.vat_rate) : x.vatRate, validDays: sub.valid_days ? String(sub.valid_days) : x.validDays, deliveryDays: sub.delivery_days != null ? String(sub.delivery_days) : "",
          deliveryTerms: sub.delivery_terms ?? x.deliveryTerms, deliveryCost: sub.delivery_cost != null ? String(sub.delivery_cost) : "", payKind: pay === "Предоплата 100%" ? "Предоплата 100%" : m || pay.startsWith("Постоплата") ? "Постоплата" : pay ? "Другое" : x.payKind,
          payDays: m ? m[1] : "", payOther: pay && !pay.startsWith("Постоплата") && pay !== "Предоплата 100%" ? pay : "", warranty: sub.warranty ?? "", comment: sub.comment ?? "" }));
      }
      setLines(init);
    }).catch((e) => setFatal(e.message));
  }, [token]);

  const tot = useMemo(() => info ? totals(info.items.map((i: any) => ({ qty: i.quantity, price: lines[i.id]?.price ?? "" })), f.vatRate, f.vatIncl) : null, [info, lines, f.vatRate, f.vatIncl]);
  const priced = info ? info.items.filter((i: any) => toMicro(lines[i.id]?.price) !== null).length : 0;
  const setLine = (id: number, patch: Partial<Line>) => setLines((l) => ({ ...l, [id]: { ...l[id], ...patch } }));
  const locked = info?.submission?.status === "ACCEPTED";

  function fail(list: string[]) {
    setErrs(list);
    setTimeout(() => errRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const problems: string[] = [];
    if (f.company.trim().length < 2) problems.push(t("errCompany"));
    if (!f.phone.trim() && !f.email.trim()) problems.push(t("errContact"));
    info.items.forEach((i: any) => { const p = lines[i.id].price; if (p && toMicro(p) === null) problems.push(t("errPrice", { name: i.name })); });
    if (!info.items.some((i: any) => lines[i.id].price.trim())) problems.push(t("errNone"));
    if (problems.length) return fail(problems);
    const payment = f.payKind === "Постоплата" ? `Постоплата${f.payDays ? ` ${f.payDays} дн.` : ""}` : f.payKind === "Другое" ? f.payOther : f.payKind;
    setBusy(true); setErrs([]);
    try {
      await call(`/api/public/rfq/${token}`, {
        company: f.company.trim(), inn: f.inn.trim() || null, contact_person: f.contact_person.trim() || null, phone: f.phone.trim() || null, email: f.email.trim() || null,
        currency: info.currency, prices_include_vat: f.vatIncl, vat_rate: f.vatRate ? f.vatRate.replace(",", ".") : null, valid_days: f.validDays ? Number(f.validDays) : null,
        delivery_days: f.deliveryDays ? Number(f.deliveryDays) : null, delivery_terms: f.deliveryTerms || null, delivery_cost: f.deliveryTerms === "Самовывоз" || !f.deliveryCost ? null : f.deliveryCost.replace(",", "."),
        payment_terms: payment || null, warranty: f.warranty || null, comment: f.comment || null,
        lines: info.items.map((i: any) => { const l = lines[i.id]; return { item_id: i.id, unit_price: l.price ? l.price.replace(/\s/g, "").replace(",", ".") : null, alt_name: l.altOpen && l.alt.trim() ? l.alt.trim() : null, note: l.note.trim() || null }; }),
      });
      setDone(true); window.scrollTo({ top: 0 });
    } catch (e: any) { fail([e.message]); } finally { setBusy(false); }
  }

  const topBar = (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div className="flex gap-1 rounded-xl bg-white/5 p-1" role="group" aria-label={t("lang")}>
        {(["ru", "uz"] as Lang[]).map((l) => <button key={l} type="button" aria-pressed={lang === l} onClick={() => chooseLang(l)} className="min-h-10 rounded-lg px-4 font-bold" style={lang === l ? { background: ORANGE, color: "#fff" } : { color: MUTED }}>{l === "ru" ? "Русский" : "O‘zbekcha"}</button>)}
      </div>
      <SizeControl label={t("size")} dark />
    </div>
  );
  const shell = (c: React.ReactNode) => <div className="min-h-screen bg-[#0b0d14] text-[#f2f4fa]" style={{ backgroundImage: "radial-gradient(1200px 500px at 85% -10%, rgba(255,106,19,.16), transparent)" }}><div className="mx-auto max-w-3xl px-4 pb-40 pt-6 sm:pt-10">{topBar}{c}</div></div>;

  if (fatal) return shell(<div className={`${card} text-center`}><h1 className="mb-3 text-2xl font-extrabold">{t("unavailable")}</h1><p className="text-lg" style={{ color: MUTED }}>{fatal}</p></div>);
  if (!info || !tot) return shell(<p className="text-lg" style={{ color: MUTED }} aria-busy="true">{t("loading")}</p>);
  if (done) return shell(
    <div className={`${card} text-center`} role="status">
      <div className="mx-auto grid h-20 w-20 place-items-center rounded-full text-5xl font-bold text-white" style={{ background: ORANGE }} aria-hidden>✓</div>
      <h1 className="mt-5 text-3xl font-extrabold">{t("thanks")}</h1>
      <p className="mx-auto mt-3 max-w-xl text-lg leading-relaxed" style={{ color: MUTED }}>{t("thanksText")}</p>
      <button className="mt-6 min-h-[3.25rem] rounded-xl border-2 border-white/25 px-6 text-lg font-bold" onClick={() => setDone(false)}>{t("change")}</button>
    </div>);

  const payLabel: Record<string, string> = { "Предоплата 100%": t("prepay"), "Постоплата": t("postpay"), "Другое": t("otherPay") };
  const delLabel: Record<string, string> = { "Доставка поставщиком": t("dSupplier"), "Самовывоз": t("dPickup"), "Транспортная компания": t("dTransport") };
  const req = <span className="ml-2 rounded-md px-1.5 py-0.5 text-xs font-bold" style={{ background: "rgba(255,106,19,.18)", color: ORANGE }}>{t("required")}</span>;
  const opt = <span className="ml-2 text-sm font-normal" style={{ color: MUTED }}>({t("optional")})</span>;

  return shell(
    <form onSubmit={submit} noValidate className="space-y-6">
      <header>
        <h1 className="text-[2rem] font-extrabold leading-tight tracking-tight sm:text-5xl">{t("title")}</h1>
        <div className="mt-3 h-1.5 w-24 rounded" style={{ background: ORANGE }} />
        <p className="mt-4 text-lg leading-relaxed" style={{ color: MUTED }}>{t("intro")}</p>
      </header>

      <div className={`${card} grid gap-4 sm:grid-cols-3`}>
        <div><div className="text-sm" style={{ color: MUTED }}>{t("purchase")}</div><div className="text-lg font-bold">{info.number}</div>{info.purpose && <div style={{ color: MUTED }}>{info.purpose}</div>}</div>
        <div><div className="text-sm" style={{ color: MUTED }}>{t("needBy")}</div><div className="text-lg font-bold">{info.need_by ? new Date(info.need_by).toLocaleDateString("ru-RU") : "—"}</div></div>
        <div><div className="text-sm" style={{ color: MUTED }}>{t("validUntil")}</div><div className="text-lg font-bold">{new Date(info.expires_at).toLocaleDateString("ru-RU")}</div></div>
        {info.message && <div className="rounded-xl bg-white/5 p-4 text-lg sm:col-span-3"><div className="mb-1 text-sm" style={{ color: MUTED }}>{t("buyerMsg")}</div>{info.message}</div>}
      </div>

      {info.submission && <p role="status" className="rounded-xl border-2 px-5 py-4 text-lg" style={{ borderColor: ORANGE }}>{locked ? t("accepted") : t("already", { n: info.submission.revision })}</p>}

      <fieldset disabled={locked} className="space-y-6 disabled:opacity-60">
        <Step n={1} id="s1" lang={lang} title={t("s1")}>
          <div className="grid gap-5 sm:grid-cols-2">
            <label className="sm:col-span-2"><span className={lbl}>{t("company")}{req}</span><input className={inp} value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} autoComplete="organization" /></label>
            <label><span className={lbl}>{t("phone")}</span><input type="tel" className={inp} value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} autoComplete="tel" placeholder="+998 __ ___ __ __" /></label>
            <label><span className={lbl}>{t("email")}</span><input type="email" className={inp} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoComplete="email" /></label>
            <p className="-mt-2 text-base sm:col-span-2" style={{ color: MUTED }}>{t("contactHelp")}</p>
            <label><span className={lbl}>{t("contactPerson")}{opt}</span><input className={inp} value={f.contact_person} onChange={(e) => setF({ ...f, contact_person: e.target.value })} autoComplete="name" /></label>
            <label><span className={lbl}>{t("inn")}{opt}</span><input inputMode="numeric" className={inp} value={f.inn} onChange={(e) => setF({ ...f, inn: e.target.value })} /></label>
          </div>
        </Step>

        <Step n={2} id="s2" lang={lang} title={t("s2")}>
          <p className="mb-5 text-lg leading-relaxed">{t("priceHelp")}</p>
          <div className="mb-6 rounded-xl bg-white/5 p-4">
            <div className="mb-3 text-lg font-semibold" id="vatq">{t("vatQuestion")}</div>
            <div className="flex flex-wrap gap-3" role="radiogroup" aria-labelledby="vatq">
              {[[true, t("withVat")], [false, t("withoutVat")]].map(([v, l]) => (
                <button type="button" key={String(v)} role="radio" aria-checked={f.vatIncl === v} onClick={() => setF({ ...f, vatIncl: v as boolean })} className="min-h-[3.25rem] flex-1 rounded-xl border-2 px-5 text-lg font-bold sm:flex-none"
                  style={f.vatIncl === v ? { background: ORANGE, borderColor: ORANGE, color: "#fff" } : { borderColor: "rgba(255,255,255,.2)", color: "#e9ecf5" }}>{f.vatIncl === v ? "✓ " : ""}{l as string}</button>
              ))}
            </div>
            <label className="mt-4 flex items-center gap-3 text-lg"><span>{t("vatRate")}</span><input inputMode="decimal" className={`${inp} !w-28`} value={f.vatRate} onChange={(e) => setF({ ...f, vatRate: e.target.value })} /></label>
            <p className="mt-3 text-base" style={{ color: MUTED }}>{t("vatHint")}</p>
          </div>

          <ul className="space-y-5">
            {info.items.map((it: any) => {
              const l = lines[it.id];
              const q = toMicro(it.quantity), p = toMicro(l.price);
              return (
                <li key={it.id} className="rounded-2xl border-2 border-white/10 p-4 sm:p-5">
                  <div className="text-[1.15rem] font-bold leading-snug"><span className="mr-2" style={{ color: ORANGE }}>{it.position}.</span>{it.name}</div>
                  {[it.code && `Арт. ${it.code}`, it.specs, it.manufacturer, it.requirements].filter(Boolean).length > 0 && <div className="mt-1 text-base" style={{ color: MUTED }}>{[it.code && `Арт. ${it.code}`, it.specs, it.manufacturer, it.requirements].filter(Boolean).join(" · ")}</div>}
                  <div className="mt-2 inline-block rounded-lg bg-white/5 px-3 py-1.5 text-lg">{t("need")}: <b>{it.quantity} {it.unit}</b></div>
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    <label><span className={lbl}>{t("pricePer")} {it.unit}</span><input inputMode="decimal" className={`${inp} !text-xl font-semibold`} placeholder={t("noStock")} value={l.price} onChange={(e) => setLine(it.id, { price: e.target.value })} aria-label={`${t("pricePer")} ${it.unit}: ${it.name}`} /></label>
                    <div><span className={lbl}>{t("sum")}</span><div className="flex min-h-[3.25rem] items-center rounded-xl bg-white/5 px-4 text-xl font-bold tabular-nums" aria-live="polite">{p != null && q != null ? showMicro(mulM(p, q)) : "—"}</div></div>
                  </div>
                  <button type="button" className="mt-4 min-h-11 text-base font-semibold underline" style={{ color: ORANGE }} onClick={() => setLine(it.id, { altOpen: !l.altOpen })}>{l.altOpen ? t("noAnalog") : t("offerAnalog")}</button>
                  {l.altOpen && <label className="mt-2 block"><span className={lbl}>{t("analogWhat")}</span><input className={inp} value={l.alt} onChange={(e) => setLine(it.id, { alt: e.target.value })} /></label>}
                  <label className="mt-3 block"><span className={lbl}>{t("note")}</span><input className={inp} value={l.note} onChange={(e) => setLine(it.id, { note: e.target.value })} /></label>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-base" style={{ color: MUTED }}>{t("emptyIsNoStock")}</p>
          <div className="mt-5 overflow-hidden rounded-xl border-2 border-white/10 text-lg" aria-live="polite">
            <div className="flex justify-between bg-white/5 px-4 py-3"><span>{t("totalNoVat")}</span><b className="tabular-nums">{showMicro(tot.net)}</b></div>
            <div className="flex justify-between border-t border-white/10 bg-white/5 px-4 py-3"><span>{t("vat")} {f.vatRate || 0}%</span><b className="tabular-nums">{showMicro(tot.vat)}</b></div>
            <div className="flex justify-between border-t border-white/10 px-4 py-4 text-xl font-extrabold" style={{ color: ORANGE }}><span>{t("totalWithVat")}</span><span className="tabular-nums">{showMicro(tot.gross)}</span></div>
          </div>
        </Step>

        <Step n={3} id="s3" lang={lang} title={t("s3")}>
          <div className="grid gap-5 sm:grid-cols-2">
            <label className="sm:col-span-2"><span className={lbl}>{t("payment")}</span>
              <select className={inp} value={f.payKind} onChange={(e) => setF({ ...f, payKind: e.target.value })}>{Object.keys(payLabel).map((k) => <option key={k} value={k}>{payLabel[k]}</option>)}</select></label>
            {f.payKind === "Постоплата" && <label><span className={lbl}>{t("payDays")}</span><input inputMode="numeric" className={inp} value={f.payDays} onChange={(e) => setF({ ...f, payDays: e.target.value })} /></label>}
            {f.payKind === "Другое" && <label className="sm:col-span-2"><span className={lbl}>{t("payOther")}</span><input className={inp} value={f.payOther} onChange={(e) => setF({ ...f, payOther: e.target.value })} /></label>}
            <label><span className={lbl}>{f.deliveryTerms === "Самовывоз" ? t("readyDays") : t("deliveryDays")}</span><input inputMode="numeric" className={inp} value={f.deliveryDays} onChange={(e) => setF({ ...f, deliveryDays: e.target.value })} /></label>
            <label><span className={lbl}>{t("delivery")}</span>
              <select className={inp} value={f.deliveryTerms} onChange={(e) => setF({ ...f, deliveryTerms: e.target.value })}>{Object.keys(delLabel).map((k) => <option key={k} value={k}>{delLabel[k]}</option>)}</select></label>
            {f.deliveryTerms === "Самовывоз"
              ? <p className="rounded-xl bg-white/5 p-4 text-lg sm:col-span-2" role="note">{t("pickupNote")}</p>
              : <label className="sm:col-span-2"><span className={lbl}>{t("deliveryCost")} ({info.currency}){opt}</span><input inputMode="decimal" className={inp} value={f.deliveryCost} onChange={(e) => setF({ ...f, deliveryCost: e.target.value })} /><span className="mt-1 block text-base" style={{ color: MUTED }}>{t("deliveryCostHint")}</span></label>}
            <label><span className={lbl}>{t("warranty")}{opt}</span><input className={inp} value={f.warranty} onChange={(e) => setF({ ...f, warranty: e.target.value })} /></label>
            <label><span className={lbl}>{t("validDays")}</span><input inputMode="numeric" className={inp} value={f.validDays} onChange={(e) => setF({ ...f, validDays: e.target.value })} /></label>
            <label className="sm:col-span-2"><span className={lbl}>{t("comment")}{opt}</span><textarea rows={3} className={inp} placeholder={t("commentPh")} value={f.comment} onChange={(e) => setF({ ...f, comment: e.target.value })} /></label>
          </div>
        </Step>
      </fieldset>

      {errs.length > 0 && (
        <div ref={errRef} role="alert" className="rounded-2xl border-2 border-red-400/60 bg-red-500/10 p-5 text-lg">
          <div className="mb-2 font-bold text-red-300">{t("fixBelow")}</div>
          <ul className="list-disc space-y-1 pl-6 text-red-200">{errs.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </div>
      )}
      <p className="text-center text-base" style={{ color: MUTED }}>{t("privacy")}</p>

      {!locked && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-white/10 bg-[#0b0d14]/95 backdrop-blur">
          <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div aria-live="polite"><div className="text-sm" style={{ color: MUTED }}>{t("totalWithVat")} · {priced} {t("items")}</div><div className="text-2xl font-extrabold tabular-nums" style={{ color: ORANGE }}>{showMicro(tot.gross)} <span className="text-base font-semibold">{info.currency}</span></div></div>
            <button disabled={busy} className="min-h-14 flex-1 rounded-2xl px-8 text-xl font-extrabold text-white disabled:opacity-60 sm:flex-none" style={{ background: ORANGE }}>{busy ? t("sending") : t("submit")}</button>
          </div>
        </div>
      )}
    </form>
  );
}
