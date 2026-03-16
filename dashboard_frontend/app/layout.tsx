import type { Metadata } from 'next'
import { Barlow_Condensed, IBM_Plex_Mono, Barlow } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { TopNav } from '@/components/TopNav'
import { ProfileProvider } from '@/lib/profiles'
import './globals.css'

const barlow = Barlow({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600'],
  variable: '--font-sans',
})

const barlowCondensed = Barlow_Condensed({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-condensed',
})

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono',
})

export const metadata: Metadata = {
  title: 'Frammer AI — Operations Center',
  description: 'Real-time video processing and publishing analytics',
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
    <html lang="en" className="dark">
      <body className={`${barlow.variable} ${barlowCondensed.variable} ${ibmPlexMono.variable} antialiased`}
            style={{ background: 'var(--void)', color: 'var(--on)' }}>
        <ProfileProvider>
          <TopNav />
          <main className="pt-11">
            {children}
          </main>
        </ProfileProvider>
        <Analytics />
      </body>
    </html>
  )
}
