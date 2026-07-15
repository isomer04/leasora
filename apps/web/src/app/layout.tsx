import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import { themeInitScript } from '@/lib/theme';
import '@/styles/globals.css';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Leasora - Lease Analysis Platform',
  description: 'Analyze and compare lease agreements with AI-powered insights',
  keywords: ['lease', 'analysis', 'ai', 'compare', 'rental'],
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        {/* Applies the persisted (or OS-preferred) theme class before first
            paint so there's no flash of the wrong theme. See lib/theme.ts. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript() }} />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
      </head>
      <body className="antialiased font-sans">
        {children}
      </body>
    </html>
  );
}
