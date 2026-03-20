'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  LayoutDashboard,
  MessageSquare,
  Newspaper,
  Zap,
  Database,
  ShieldCheck,
  LogOut,
  LogIn,
  Users,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface StoredUser {
  user_id: string;
  email: string;
  role: string;
  user_profile: string;
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<StoredUser | null>(null);

  useEffect(() => {
    const raw = localStorage.getItem('auth_user');
    if (raw) {
      try { setUser(JSON.parse(raw)); } catch { /* ignore */ }
    }
    // Re-read on storage changes (e.g. login in another tab)
    const handler = () => {
      const r = localStorage.getItem('auth_user');
      try { setUser(r ? JSON.parse(r) : null); } catch { setUser(null); }
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);

  function handleLogout() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    setUser(null);
    router.push('/login');
  }

  const links = [
    { href: '/dashboard',  label: 'Dashboard',               icon: LayoutDashboard },
    { href: '/narrator',   label: 'Insight Narrator',         icon: Newspaper },
    { href: '/query',      label: 'Natural Language Query',   icon: MessageSquare },
    { href: '/kpi-lab',    label: 'KPI Lab',                  icon: Zap },
    { href: '/data',       label: 'Data Manager',             icon: Database },
    { href: '/workspace',  label: 'Workspace',                icon: Users },
  ];

  return (
    <div className="w-64 bg-sidebar border-r border-sidebar-border flex flex-col h-screen fixed left-0 top-0">
      {/* Logo */}
      <div className="p-6 border-b border-sidebar-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center">
            <div className="text-primary-foreground font-bold text-lg">F</div>
          </div>
          <div className="flex flex-col">
            <span className="font-bold text-sidebar-foreground">Frammer</span>
            <span className="text-xs text-muted-foreground">AI Analytics</span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-6 space-y-2 overflow-y-auto">
        {links.map((link) => {
          const Icon = link.icon;
          const isActive = pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                'flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 font-medium',
                isActive
                  ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/30'
                  : 'text-sidebar-foreground hover:bg-sidebar-accent'
              )}
            >
              <Icon className="w-5 h-5" />
              <span>{link.label}</span>
            </Link>
          );
        })}

        {/* Admin Console — only shown for admin role */}
        {user?.role === 'admin' && (
          <Link
            href="/admin"
            className={cn(
              'flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 font-medium border mt-4',
              pathname.startsWith('/admin')
                ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/30 border-primary'
                : 'text-primary border-primary/30 hover:bg-primary/10'
            )}
          >
            <ShieldCheck className="w-5 h-5" />
            <span>Admin Console</span>
          </Link>
        )}
      </nav>

      {/* Footer — user info + logout */}
      <div className="p-6 border-t border-sidebar-border space-y-3">
        {user ? (
          <>
            <div className="text-xs space-y-0.5">
              <p className="font-semibold text-sidebar-foreground truncate">{user.email}</p>
              <div className="flex items-center gap-2">
                <span className={cn(
                  'px-1.5 py-0.5 rounded text-xs font-medium',
                  user.role === 'admin'
                    ? 'bg-primary/20 text-primary'
                    : 'bg-muted text-muted-foreground'
                )}>
                  {user.role}
                </span>
                {user.user_profile !== 'basic' && (
                  <span className="text-muted-foreground">{user.user_profile}</span>
                )}
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 text-muted-foreground hover:text-foreground text-xs w-full"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign out
            </button>
          </>
        ) : (
          <Link
            href="/login"
            className="flex items-center gap-2 text-muted-foreground hover:text-foreground text-xs"
          >
            <LogIn className="w-3.5 h-3.5" />
            Sign in
          </Link>
        )}
      </div>
    </div>
  );
}
