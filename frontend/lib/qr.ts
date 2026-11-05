import qrcode from "./vendor/qrcode.js";

/** QR code as a scalable SVG string (white background, good contrast for any phone camera). */
export function qrSvg(text: string, title = "QR-код"): string {
  const q = qrcode(0, "M");
  q.addData(text);
  q.make();
  return q.createSvgTag({ cellSize: 8, margin: 24, scalable: true, title });
}

/** Save the QR as a PNG file (works offline, no server round-trip). */
export async function downloadQrPng(svg: string, filename: string) {
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  const img = new Image();
  await new Promise<void>((ok, fail) => { img.onload = () => ok(); img.onerror = () => fail(new Error("QR")); img.src = url; });
  const canvas = Object.assign(document.createElement("canvas"), { width: 1024, height: 1024 });
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, 1024, 1024);
  ctx.drawImage(img, 0, 0, 1024, 1024);
  URL.revokeObjectURL(url);
  canvas.toBlob((b) => {
    if (!b) return;
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(b), download: filename });
    a.click();
    URL.revokeObjectURL(a.href);
  }, "image/png");
}
