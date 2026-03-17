'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useProfile, PROFILES, PROFILE_KEYS, type ProfileKey } from '@/lib/profiles';

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
  { href: '/recommendations', label: 'Recs' },
  { href: '/kpi-lab',  label: 'KPI Lab' },
];

export function TopNav() {
  const pathname = usePathname();
  const { profile, profileDef, setProfile } = useProfile();
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
      className="fixed top-0 left-0 right-0 z-50"
      style={{
        background: 'rgba(245, 241, 235, 0.92)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderBottom: '1px solid var(--wire)',
        boxShadow: '0 1px 0 rgba(43, 35, 32, 0.04)',
      }}
    >
      {/* Terracotta accent line */}
      <div style={{
        height: '3px',
        background: 'linear-gradient(90deg, var(--signal) 0%, #D4864B 60%, rgba(196, 85, 58, 0.2) 100%)',
      }} />

      <div className="flex items-stretch" style={{ height: '52px' }}>

        {/* Brand */}
        <div
          className="flex items-center shrink-0"
          style={{ padding: '0 24px', borderRight: '1px solid var(--wire)', gap: '10px' }}
        >
          {/* Mark */}
          <div style={{
            width: '26px',
            height: '26px',
            borderRadius: '8px',
            background: 'var(--signal)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}>
            <span style={{ color: '#fff', fontSize: '0.65rem', fontWeight: 800, letterSpacing: '-0.02em', fontFamily: 'var(--font-sans)' }}>F</span>
          </div>
          <div>
            <div style={{
              fontFamily: 'var(--font-display)',
              fontSize: '1rem',
              fontWeight: 700,
              color: 'var(--on)',
              lineHeight: 1.1,
              letterSpacing: '0.01em',
            }}>
              Frammer
            </div>
            <div style={{
              fontFamily: 'var(--font-sans)',
              fontSize: '0.55rem',
              fontWeight: 600,
              color: 'var(--on-low)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              lineHeight: 1,
            }}>
              Analytics
            </div>
          </div>
        </div>

        {/* Dashboard nav — pill tabs */}
        <nav
          className="flex items-center"
          style={{ padding: '0 16px', gap: '4px', borderRight: '1px solid var(--wire)' }}
        >
          {SECTION_LINKS.map((link) => {
            const active = isActiveSection(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: '0.78rem',
                  fontWeight: active ? 700 : 500,
                  color: active ? 'var(--signal)' : 'var(--on-mid)',
                  padding: '5px 12px',
                  borderRadius: '20px',
                  background: active ? 'var(--signal-dim)' : 'transparent',
                  border: active ? '1px solid rgba(196, 85, 58, 0.2)' : '1px solid transparent',
                  transition: 'all 0.18s ease',
                  textDecoration: 'none',
                  whiteSpace: 'nowrap' as const,
                  cursor: 'pointer',
                }}
                onMouseEnter={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLElement).style.color = 'var(--on)';
                    (e.currentTarget as HTMLElement).style.background = 'var(--surface-raise)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLElement).style.color = 'var(--on-mid)';
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }
                }}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        {/* Tools — smaller, secondary style */}
        <nav
          className="flex items-center"
          style={{ padding: '0 12px', gap: '2px' }}
        >
          {TOOL_LINKS.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: '0.72rem',
                  fontWeight: active ? 700 : 500,
                  color: active ? 'var(--uplink)' : 'var(--on-low)',
                  padding: '4px 10px',
                  borderRadius: '20px',
                  background: active ? 'rgba(91, 126, 161, 0.1)' : 'transparent',
                  border: active ? '1px solid rgba(91, 126, 161, 0.2)' : '1px solid transparent',
                  transition: 'all 0.18s ease',
                  textDecoration: 'none',
                  whiteSpace: 'nowrap' as const,
                }}
                onMouseEnter={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLElement).style.color = 'var(--on-mid)';
                    (e.currentTarget as HTMLElement).style.background = 'var(--surface-raise)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLElement).style.color = 'var(--on-low)';
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }
                }}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Profile selector */}
        <div
          ref={dropdownRef}
          className="flex items-center shrink-0 relative"
          style={{ borderLeft: '1px solid var(--wire)' }}
        >
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '0 20px',
              height: '100%',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-raise)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
          >
            <span
              style={{
                fontSize: '0.9rem',
                width: '30px',
                height: '30px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'var(--signal-dim)',
                borderRadius: '10px',
                color: 'var(--signal)',
                border: '1px solid rgba(196, 85, 58, 0.15)',
              }}
            >
              {profileDef.icon}
            </span>
            <div style={{ textAlign: 'left' }}>
              <div style={{
                fontFamily: 'var(--font-sans)',
                fontSize: '0.78rem',
                fontWeight: 700,
                color: 'var(--on)',
                lineHeight: 1.2,
              }}>
                {profileDef.displayName}
              </div>
              <div style={{
                fontFamily: 'var(--font-sans)',
                fontSize: '0.6rem',
                color: 'var(--on-low)',
                lineHeight: 1,
              }}>
                {profileDef.focus}
              </div>
            </div>
            <span style={{ color: 'var(--on-low)', fontSize: '0.6rem', marginLeft: '2px' }}>&#9662;</span>
          </button>

          {dropdownOpen && (
            <div
              style={{
                position: 'absolute',
                top: 'calc(100% + 6px)',
                right: '8px',
                background: 'var(--surface)',
                border: '1px solid var(--wire)',
                borderRadius: '16px',
                minWidth: '260px',
                zIndex: 100,
                boxShadow: '0 12px 40px rgba(43, 35, 32, 0.14), 0 2px 8px rgba(43, 35, 32, 0.06)',
                overflow: 'hidden',
              }}
            >
              <div style={{ padding: '10px 14px 8px', borderBottom: '1px solid var(--wire)' }}>
                <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.62rem', fontWeight: 700, color: 'var(--on-low)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                  Switch Profile
                </span>
              </div>
              {PROFILE_KEYS.map((key) => {
                const p = PROFILES[key];
                const isActive = profile === key;
                return (
                  <button
                    key={key}
                    onClick={() => { setProfile(key as ProfileKey); setDropdownOpen(false); }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '10px 14px',
                      width: '100%',
                      background: isActive ? 'var(--signal-dim)' : 'transparent',
                      border: 'none',
                      borderBottom: '1px solid var(--wire)',
                      cursor: 'pointer',
                      transition: 'background 0.15s',
                      textAlign: 'left',
                    }}
                    onMouseEnter={(e) => { if (!isActive) (e.currentTarget as HTMLElement).style.background = 'var(--surface-raise)'; }}
                    onMouseLeave={(e) => { if (!isActive) (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                  >
                    <span
                      style={{
                        fontSize: '0.85rem',
                        width: '32px',
                        height: '32px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: isActive ? 'var(--signal-dim)' : 'var(--surface-hi)',
                        borderRadius: '10px',
                        color: isActive ? 'var(--signal)' : 'var(--on-low)',
                        border: isActive ? '1px solid rgba(196, 85, 58, 0.2)' : '1px solid var(--wire)',
                        flexShrink: 0,
                      }}
                    >
                      {p.icon}
                    </span>
                    <div>
                      <div style={{
                        fontFamily: 'var(--font-sans)',
                        fontSize: '0.82rem',
                        fontWeight: isActive ? 700 : 600,
                        color: isActive ? 'var(--signal)' : 'var(--on)',
                      }}>
                        {p.displayName}
                      </div>
                      <div style={{
                        fontFamily: 'var(--font-sans)',
                        fontSize: '0.65rem',
                        color: 'var(--on-low)',
                        marginTop: '1px',
                      }}>
                        {p.focus}
                      </div>
                    </div>
                    {isActive && (
                      <span style={{ marginLeft: 'auto', color: 'var(--signal)', fontSize: '0.7rem' }}>✓</span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Live indicator */}
        <div
          className="flex items-center gap-2"
          style={{ padding: '0 18px', borderLeft: '1px solid var(--wire)', flexShrink: 0 }}
        >
          <div className="live-dot" />
          <span style={{
            fontFamily: 'var(--font-sans)',
            fontSize: '0.7rem',
            fontWeight: 600,
            color: 'var(--ok)',
            letterSpacing: '0.04em',
          }}>
            Live
          </span>
        </div>
      </div>
    </header>
  );
}
