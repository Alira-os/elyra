import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Merimee Digital Solutions | Web Design & Marketing",
  description: "Mission-driven web design, mobile apps, and brand messaging for purpose-led organizations.",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">{children}</body>
    </html>
  );
}
