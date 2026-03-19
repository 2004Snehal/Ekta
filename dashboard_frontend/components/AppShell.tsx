1'use client';

import { usePathname } from 'next/navigation';
import { Sidebar } from './Sidebar';

const NO_SIDEBAR_PATHS = ['/login', '/signup'];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const hideSidebar = NO_SIDEBAR_PATHS.some((p) => pathname.startsWith(p));

  if (hideSidebar) {
    return <>{children}</>;
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 w-full">{children}</main>
    </div>
  );
}
