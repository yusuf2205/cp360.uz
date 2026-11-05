declare function qrcode(typeNumber: number, errorCorrectionLevel: "L" | "M" | "Q" | "H"): {
  addData(data: string): void;
  make(): void;
  createSvgTag(opts: { cellSize?: number; margin?: number; scalable?: boolean; alt?: string; title?: string }): string;
};
export default qrcode;
