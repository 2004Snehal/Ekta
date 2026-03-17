'use client';

import { ChartRenderer } from '@/components/ChartRenderer';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { DashboardKpiDetail } from '@/types/dashboard';

interface KPIDetailModalProps {
  open: boolean;
  detail: DashboardKpiDetail | null;
  onOpenChange: (open: boolean) => void;
}

export function KPIDetailModal({ open, detail, onOpenChange }: KPIDetailModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[90vh] overflow-y-auto sm:max-w-5xl"
        style={{ background: 'var(--surface)', borderRadius: '20px', border: '1px solid var(--wire)', boxShadow: '0 24px 64px rgba(43, 35, 32, 0.15)' }}
      >
        {detail ? (
          <>
            <DialogHeader>
              <DialogTitle style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', color: 'var(--on)' }}>
                {detail.title}
              </DialogTitle>
              <DialogDescription style={{ fontFamily: 'var(--font-sans)', color: 'var(--on-mid)' }}>
                {detail.subtitle}
              </DialogDescription>
            </DialogHeader>

            <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-mid)', lineHeight: 1.6 }}>
              {detail.description}
            </p>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {detail.stats.map((stat) => (
                <div
                  key={`${detail.kpiId}-${stat.label}`}
                  style={{
                    borderRadius: '14px',
                    border: '1px solid var(--wire)',
                    background: 'var(--surface-hi)',
                    padding: '16px 20px',
                  }}
                >
                  <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', fontWeight: 600, color: 'var(--on-low)', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '8px' }}>
                    {stat.label}
                  </p>
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: '1.6rem', fontWeight: 600, color: 'var(--on)' }}>
                    {stat.value}
                  </p>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              {detail.charts.map((chart, index) => (
                <ChartRenderer key={`${detail.kpiId}-${index}`} chart={chart} />
              ))}
            </div>

            <div style={{ borderRadius: '14px', border: '1px solid var(--wire)', background: 'var(--surface)', padding: '20px 24px' }}>
              <h4 style={{ fontFamily: 'var(--font-display)', fontSize: '1rem', fontWeight: 700, color: 'var(--on)', marginBottom: '16px' }}>
                {detail.tableTitle}
              </h4>
              <ChartRenderer chart={{ chart_type: 'table', title: '', data: detail.table }} />
            </div>
          </>
        ) : (
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-low)' }}>
            Select a KPI to view detail.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
