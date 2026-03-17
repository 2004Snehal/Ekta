'use client';

import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbSeparator,
  BreadcrumbPage,
} from '@/components/ui/breadcrumb';

const SOURCE_LABELS: Record<string, { label: string; href: string }> = {
  summary:  { label: 'Summary',  href: '/dashboard' },
  analysis: { label: 'Analysis', href: '/dashboard/analysis' },
  funnel:   { label: 'Funnel',   href: '/dashboard/funnel' },
  usage:    { label: 'Usage',    href: '/dashboard/usage' },
};

interface DrillBreadcrumbProps {
  source: string | null;
  currentPage: string;
  filters?: Record<string, string>;
}

export function DrillBreadcrumb({ source, currentPage, filters }: DrillBreadcrumbProps) {
  if (!source) return null;

  const src = SOURCE_LABELS[source] ?? { label: source, href: '/dashboard' };
  const filterEntries = filters ? Object.entries(filters) : [];

  return (
    <div className="flex items-center gap-3 flex-wrap" style={{ padding: '8px 0' }}>
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href={src.href} style={{ fontFamily: 'var(--font-sans)', fontSize: '0.75rem', color: 'var(--uplink)' }}>
              {src.label}
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage style={{ fontFamily: 'var(--font-sans)', fontSize: '0.75rem' }}>
              {currentPage}
            </BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {filterEntries.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {filterEntries.map(([key, value]) => (
            <span
              key={key}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.62rem',
                padding: '2px 8px',
                borderRadius: '9999px',
                background: 'var(--signal-dim)',
                color: 'var(--on-mid)',
                border: '1px solid var(--wire)',
              }}
            >
              {key}: {value}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
