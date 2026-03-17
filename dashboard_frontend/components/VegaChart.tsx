'use client';

import { useEffect, useRef } from 'react';

interface Props {
  spec: Record<string, unknown>;
  title?: string;
}

export function VegaChart({ spec, title }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !spec) return;

    let cancelled = false;

    import('vega-embed').then(({ default: embed }) => {
      if (cancelled || !containerRef.current) return;
      embed(containerRef.current, spec as never, {
        actions: false,
        theme: 'dark',
        config: {
          background: 'transparent',
          axis: { labelColor: '#9CA3AF', titleColor: '#9CA3AF', gridColor: '#2B2B2B', domainColor: '#374151' },
          legend: { labelColor: '#9CA3AF', titleColor: '#9CA3AF' },
          title: { color: '#F9FAFB' },
          view: { stroke: 'transparent' },
        },
      }).catch(console.error);
    });

    return () => {
      cancelled = true;
    };
  }, [spec]);

  return (
    <div className="bg-card border border-border rounded-lg p-4">
      {title && <p className="text-sm font-medium text-foreground mb-3">{title}</p>}
      <div ref={containerRef} className="w-full overflow-x-auto" />
    </div>
  );
}
