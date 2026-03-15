'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, MessageSquare, Zap, Database, Lightbulb } from 'lucide-react';
import { cn } from '@/lib/utils';

export function Sidebar() {
  const pathname = usePathname();

  const links = [
    { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/query', label: 'Natural Language Query', icon: MessageSquare },
    { href: '/kpi-lab', label: 'KPI Lab', icon: Zap },
    { href: '/data', label: 'Data Manager', icon: Database },
    { href: '/recommendations', label: 'Recommendations', icon: Lightbulb },
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
      <nav className="flex-1 p-6 space-y-2">
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
      </nav>

      {/* Footer */}
      <div className="p-6 border-t border-sidebar-border">
        <div className="text-xs text-muted-foreground space-y-2">
          <p className="font-semibold text-sidebar-foreground">Analytics Platform</p>
          <p>Real-time video processing and publishing analytics for Frammer AI</p>
        </div>
      </div>
    </div>
  );
}
