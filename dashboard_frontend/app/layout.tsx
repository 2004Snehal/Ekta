import type { Metadata } from 'next'
import { Plus_Jakarta_Sans, JetBrains_Mono, Playfair_Display } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { TopNav } from '@/components/TopNav'
import { ProfileProvider } from '@/lib/profiles'
import './globals.css'

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700', '800'],
  variable: '--font-sans',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono',
})

const playfair = Playfair_Display({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-display',
})

export const metadata: Metadata = {
  title: 'Frammer AI — Analytics Studio',
  description: 'Video processing and publishing analytics',
  icons: {
    icon: [
      { url: '/icon-light-32x32.png', media: '(prefers-color-scheme: light)' },
      { url: '/icon-dark-32x32.png',  media: '(prefers-color-scheme: dark)'  },
      { url: '/icon.svg', type: 'image/svg+xml' },
    ],
    apple: '/apple-icon.png',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${plusJakarta.variable} ${jetbrainsMono.variable} ${playfair.variable} antialiased`}
            style={{ background: 'var(--void)', color: 'var(--on)' }}>
        <ProfileProvider>
          <TopNav />
          <main className="pt-[55px]">
            {children}
          </main>
        </ProfileProvider>
        <Analytics />
      </body>
    </html>
  )
}
