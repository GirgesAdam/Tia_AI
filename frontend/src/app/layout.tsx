import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Tia AI", description: "Clinic operations & AI customer service" };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="ar" dir="rtl"><body>{children}</body></html>;
}
