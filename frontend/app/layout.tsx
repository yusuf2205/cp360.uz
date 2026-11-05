import type { Metadata, Viewport } from "next";
import { SIZE_BOOT } from "@/lib/size";
import "./globals.css";

export const metadata: Metadata = { title: "cp360.uz", description: "Сравнительные листы закупок" };
export const viewport: Viewport = { width: "device-width", initialScale: 1 }; // never block pinch-zoom: some users need it

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <head><script dangerouslySetInnerHTML={{ __html: SIZE_BOOT }} /></head>
      <body className="bg-background text-foreground antialiased min-h-screen">
        {children}
        <noscript><p style={{ padding: 24 }}>Для работы cp360.uz необходим включённый JavaScript.</p></noscript>
      </body>
    </html>
  );
}
