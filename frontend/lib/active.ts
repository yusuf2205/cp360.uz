"use client";
import { useCallback, useEffect, useState } from "react";

/** The procurement the user is currently working on (shared by the 3-step flow). Remembered per browser. */
export function useActive() {
  const [pid, setPidState] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("p");
    let v = fromUrl;
    try { v = v || localStorage.getItem("cp_active"); } catch {}
    if (v && Number(v)) setPidState(Number(v));
    if (fromUrl) try { localStorage.setItem("cp_active", fromUrl); } catch {}
    setReady(true);
  }, []);
  const set = useCallback((id: number | null) => {
    try { id ? localStorage.setItem("cp_active", String(id)) : localStorage.removeItem("cp_active"); } catch {}
    setPidState(id);
  }, []);
  return { pid, set, ready };
}
