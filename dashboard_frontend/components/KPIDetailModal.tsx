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
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl">
        {detail ? (
          <>
            <DialogHeader>
              <DialogTitle>{detail.title}</DialogTitle>
              <DialogDescription>{detail.subtitle}</DialogDescription>
            </DialogHeader>

            <p className="text-sm text-muted-foreground">{detail.description}</p>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {detail.stats.map((stat) => (
                <div key={`${detail.kpiId}-${stat.label}`} className="rounded-lg border border-border bg-secondary/20 p-4">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">{stat.label}</p>
                  <p className="mt-2 text-2xl font-semibold text-foreground">{stat.value}</p>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {detail.charts.map((chart, index) => (
                <ChartRenderer key={`${detail.kpiId}-${index}`} chart={chart} />
              ))}
            </div>

            <div className="rounded-lg border border-border bg-card p-5">
              <h4 className="mb-4 text-base font-semibold text-foreground">{detail.tableTitle}</h4>
              <ChartRenderer chart={{ chart_type: 'table', title: '', data: detail.table }} />
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Select a KPI to view detail.</p>
        )}
      </DialogContent>
    </Dialog>
  );
}
