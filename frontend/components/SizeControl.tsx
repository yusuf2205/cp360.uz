"use client";
import { useEffect, useState } from "react";
import { applySize, getSizeIndex } from "@/lib/size";

/** Three "А" buttons of growing size: the most recognisable control for people of any age. */
export default function SizeControl({ label = "Размер текста", dark = false }: { label?: string; dark?: boolean }) {
  const [i, setI] = useState(0);
  useEffect(() => { setI(getSizeIndex()); }, []);
  return (
    <div className="flex items-center gap-2" role="group" aria-label={label}>
      <span className={`text-sm ${dark ? "text-[#aab2c8]" : "text-muted"}`}>{label}</span>
      {[0, 1, 2].map((n) => (
        <button key={n} type="button" aria-label={`${label}: ${["обычный", "крупный", "очень крупный"][n]}`} aria-pressed={i === n}
          onClick={() => { setI(n); applySize(n); }}
          className={`grid h-10 w-10 place-items-center rounded-lg border font-bold leading-none ${i === n ? "border-primary bg-primary text-white" : dark ? "border-white/20 text-[#e9ecf5]" : "border-line bg-card"}`}
          style={{ fontSize: `${[14, 18, 22][n]}px` }}>А</button>
      ))}
    </div>
  );
}
