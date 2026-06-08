import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Merimee Digital Solutions — Custom Websites for Mission-Driven Organizations',
  description:
    'I help mission-driven organizations build beautiful, modern websites that reflect the soul of their work. Let\u2019s bring your vision to life.',
  metadataBase: new URL('https://merimeesolutions.com'),
  openGraph: {
    title: 'Merimee Digital Solutions',
    description: 'Custom websites for mission-driven organizations.',
    type: 'website',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
