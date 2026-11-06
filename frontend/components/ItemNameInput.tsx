"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type Sug = { name: string; unit: string; specs: string | null; code: string | null; manufacturer: string | null };

/** Item name field that offers items from earlier purchases; picking one fills name, unit and specs. */
export default function ItemNameInput({ value, onChange, onPick, className = "field", placeholder }: {
  value: string; onChange: (v: string) => void; onPick: (s: Sug) => void; className?: string; placeholder?: string;
}) {
  const [list, setList] = useState<Sug[]>([]);
  const [open, setOpen] = useState(false);
  const skip = useRef(false);

  useEffect(() => {
    if (skip.current) { skip.current = false; return; }
    if (value.trim().length < 2) { setList([]); return; }
    const h = setTimeout(() => api(`/api/history/items?q=${encodeURIComponent(value.trim())}`).then((r) => { setList(r); setOpen(true); }).catch(() => setList([])), 250);
    return () => clearTimeout(h);
  }, [value]);

  return (
    <div className="relative sm:col-span-3">
      <input required aria-label="Наименование" aria-autocomplete="list" autoComplete="off" className={className} placeholder={placeholder}
        value={value} onChange={(e) => onChange(e.target.value)} onBlur={() => setTimeout(() => setOpen(false), 150)} onFocus={() => list.length && setOpen(true)} />
      {open && list.length > 0 && (
        <ul role="listbox" className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-xl border border-line bg-card p-1 shadow-lg">
          <li className="px-3 py-1 text-xs text-muted">Вы уже закупали, нажмите чтобы подставить:</li>
          {list.map((s, i) => (
            <li key={i}>
              <button type="button" role="option" aria-selected={false} className="w-full rounded-lg px-3 py-2 text-left hover:bg-primary-soft focus:bg-primary-soft"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => { skip.current = true; onPick(s); setOpen(false); }}>
                <span className="font-semibold">{s.name}</span> <span className="text-xs text-muted">· {s.unit}{s.specs ? ` · ${s.specs}` : ""}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
