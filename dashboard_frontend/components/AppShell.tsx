'use client';

import { usePathname } from 'next/navigation';
import { Sidebar } from '@/components/Sidebar';

const AUTH_PATHS = ['/login', '/register'];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAuthPage = AUTH_PATHS.some((p) => pathname.startsWith(p));

  if (isAuthPage) {
    return <>{children}</>;
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 w-full">{children}</main>
    </div>
  );
}
