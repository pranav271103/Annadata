import type { Metadata } from 'next';
import Image from 'next/image';
import './globals.css';

export const metadata: Metadata = {
  title: 'Annadata – Agricultural Intelligence for India',
  description:
    'UX4G-inspired Indian agriculture platform for climate-smart crop and protein optimization.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="ux4g-body">
        {children}
      </body>
    </html>
  );
}
