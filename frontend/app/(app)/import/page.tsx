"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ImportWorkspace from "@/components/ImportWorkspace";
import { ActiveBar, NoActive, PageHead } from "@/components/Flow";
import { api } from "@/lib/api";
import { useActive } from "@/lib/active";

export default function ImportPage() {
  const { pid, set, ready } = useActive();
  const [p, setP] = useState<any>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => {
    if (!pid) return;
    api(`/api/procurements/${pid}`).then(setP).catch((e) => (e.status === 404 ? set(null) : setErr(e.message)));
  }, [pid, set]);
  useEffect(() => { load(); }, [load]);
  if (!ready) return null;
  return (
    <div>
      <PageHead step={1} title="Умный импорт" subtitle="Получили коммерческое предложение? Просто добавьте его сюда."
        help="Добавьте предложения поставщиков любым способом: перетащите файл, вставьте текст, впишите цены вручную или отправьте поставщику ссылку. Когда закончите — нажмите «Перейти к сравнению»."
        right={pid ? <Link href="/compare" className="btn">Перейти к сравнению →</Link> : undefined} />
      {!pid ? <NoActive onPick={set} /> : (
        <>
          <ActiveBar pid={pid} onPick={set} />
          {err && <p role="alert" className="mb-3 text-sm text-red-600">{err}</p>}
          {p ? <ImportWorkspace key={p.id} p={p} reload={load} /> : <div className="h-64 animate-pulse rounded-2xl bg-primary-soft/40" />}
        </>
      )}
    </div>
  );
}
