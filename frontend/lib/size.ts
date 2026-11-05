/** User-selectable text size. Everything is rem-based, so changing the root size scales the whole interface. */
export const SIZES = [17, 20, 24];

export function getSizeIndex(): number {
  try {
    const v = Number(localStorage.getItem("cp_size"));
    return v >= 0 && v < SIZES.length ? v : 0;
  } catch {
    return 0;
  }
}

export function applySize(i: number) {
  document.documentElement.style.fontSize = SIZES[i] + "px";
  try { localStorage.setItem("cp_size", String(i)); } catch {}
}

/** Inline script for <head>: applies the saved size before first paint (no flash of small text). */
export const SIZE_BOOT = `try{var i=Number(localStorage.getItem("cp_size"));if(i>0&&i<3)document.documentElement.style.fontSize=[17,20,24][i]+"px"}catch(e){}`;
