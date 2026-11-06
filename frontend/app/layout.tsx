import type { Metadata, Viewport } from "next";
import { SIZE_BOOT } from "@/lib/size";
import "./globals.css";

export const metadata: Metadata = {
  title: "cp360.uz", description: "Сравнительные листы закупок",
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
  appleWebApp: { capable: true, title: "cp360", statusBarStyle: "default" },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#2745e8" }; // never block pinch-zoom: some users need it

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
