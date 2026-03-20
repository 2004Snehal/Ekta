'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useProfile, PROFILES, PROFILE_KEYS, type ProfileKey } from '@/lib/profiles';
import { useAuth } from '@/context/AuthContext';

const SECTION_LINKS = [
  { href: '/dashboard',          label: 'Summary' },
  { href: '/dashboard/usage',    label: 'Usage' },
  { href: '/dashboard/analysis', label: 'Analysis' },
  { href: '/dashboard/funnel',   label: 'Funnel' },
  { href: '/dashboard/explorer', label: 'Explorer' },
];

const TOOL_LINKS = [
  { href: '/query',    label: 'NLQ' },
  { href: '/narrator', label: 'Insights' },
  { href: '/kpi-lab',  label: 'KPI Lab' },
  { href: '/workspace', label: 'Workspace' },
];

export function TopNav() {
  const pathname = usePathname();
  const { profile, profileDef, setProfile } = useProfile();
  const { user } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const isActiveSection = (href: string) => {
    if (href === '/dashboard') return pathname === '/dashboard';
    return pathname.startsWith(href);
  };

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 flex items-stretch h-11"
      style={{ background: 'var(--void)', borderBottom: '1px solid var(--wire)' }}
    >
      {/* Brand */}
      <div
        className="flex items-center px-5 shrink-0"
        style={{ borderRight: '1px solid var(--wire)' }}
      >
        <span
          style={{
            fontFamily: 'var(--font-condensed)',
            fontSize: '0.8rem',
            fontWeight: 700,
            letterSpacing: '0.22em',
            color: 'var(--signal)',
            userSelect: 'none',
          }}
        >
          ▌FRAMMER
        </span>
      </div>

      {/* Profile selector */}
      <div
        ref={dropdownRef}
        className="flex items-center shrink-0 relative"
        style={{ borderRight: '1px solid var(--wire)' }}
      >
        <button
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className="flex items-center gap-2 px-4 h-full"
          style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
        >
          <span
            style={{
              fontFamily: 'var(--font-condensed)',
              fontSize: '0.55rem',
              fontWeight: 700,
              letterSpacing: '0.14em',
              color: 'var(--signal)',
              width: '18px',
              height: '18px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px solid var(--signal)',
            }}
          >
            {profileDef.icon}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-condensed)',
              fontSize: '0.6rem',
              fontWeight: 700,
              letterSpacing: '0.14em',
              color: 'var(--on-mid)',
              textTransform: 'uppercase',
            }}
          >
            {profileDef.displayName}
          </span>
          <span style={{ color: 'var(--on-low)', fontSize: '0.5rem' }}>▾</span>
        </button>

        {dropdownOpen && (
          <div
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              background: 'var(--surface)',
              border: '1px solid var(--wire)',
              minWidth: '220px',
              zIndex: 100,
            }}
          >
            {PROFILE_KEYS.map((key) => {
              const p = PROFILES[key];
              return (
                <button
                  key={key}
                  onClick={() => { setProfile(key as ProfileKey); setDropdownOpen(false); }}
                  className="w-full text-left"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '8px 14px',
                    background: profile === key ? 'var(--surface-raise)' : 'transparent',
                    border: 'none',
                    borderBottom: '1px solid var(--wire)',
                    cursor: 'pointer',
                  }}
                >
                  <span
                    style={{
                      fontFamily: 'var(--font-condensed)',
                      fontSize: '0.55rem',
                      fontWeight: 700,
                      color: profile === key ? 'var(--signal)' : 'var(--on-low)',
                      width: '18px',
                      height: '18px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      border: `1px solid ${profile === key ? 'var(--signal)' : 'var(--wire-hi)'}`,
                    }}
                  >
                    {p.icon}
                  </span>
                  <div>
                    <div style={{
                      fontFamily: 'var(--font-condensed)',
                      fontSize: '0.65rem',
                      fontWeight: 600,
                      letterSpacing: '0.1em',
                      color: profile === key ? 'var(--on)' : 'var(--on-mid)',
                      textTransform: 'uppercase',
                    }}>
                      {p.displayName}
                    </div>
                    <div style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.5rem',
                      color: 'var(--on-low)',
                      marginTop: '1px',
                    }}>
                      {p.focus}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Section tabs */}
      <nav className="flex items-center gap-5 px-5 flex-1">
        {SECTION_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={cn('nav-link', isActiveSection(link.href) && 'active')}
          >
            {link.label}
          </Link>
        ))}

        <div className="wire-v" style={{ height: '14px' }} />

        {TOOL_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={cn('nav-link', pathname.startsWith(link.href) && 'active')}
          >
            {link.label}
          </Link>
        ))}

        {user?.role === 'admin' && (
          <>
            <div className="wire-v" style={{ height: '14px' }} />
            <Link
              href="/admin"
              className={cn('nav-link', pathname.startsWith('/admin') && 'active')}
              style={{ color: 'var(--signal)' }}
            >
              Admin
            </Link>
          </>
        )}
      </nav>

      {/* Right: live indicator */}
      <div
        className="flex items-center gap-2 px-5 shrink-0"
        style={{ borderLeft: '1px solid var(--wire)' }}
      >
        <div className="live-dot" />
        <span
          style={{
            fontFamily: 'var(--font-condensed)',
            fontSize: '0.6rem',
            fontWeight: 700,
            letterSpacing: '0.2em',
            color: 'var(--on-low)',
          }}
        >
          LIVE
        </span>
      </div>
    </header>
  );
}
