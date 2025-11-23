import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Protein Engineering Platform',
  description: 'AI-powered molecular crop optimization',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
