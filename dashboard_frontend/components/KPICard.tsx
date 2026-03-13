'use client';

import { ArrowUp, ArrowDown, TrendingUp } from 'lucide-react';

interface KPICardProps {
  title: string;
  value: string | number;
  change: number;
  timeframe: string;
  icon?: React.ReactNode;
  onClick?: () => void;
}

export function KPICard({ title, value, change, timeframe, icon, onClick }: KPICardProps) {
  const isPositive = change >= 0;
  const clickable = Boolean(onClick);

  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-lg border border-border bg-card p-6 text-left transition-all duration-300 ${
        clickable
          ? 'hover:border-primary/50 hover:shadow-lg hover:shadow-primary/10 focus:outline-none focus:ring-2 focus:ring-primary/40'
          : ''
      }`}
    >
      <div className="mb-4 flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{title}</p>
          <h3 className="mt-2 text-3xl font-bold text-foreground">{value}</h3>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          {icon || <TrendingUp className="h-5 w-5" />}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className={`flex items-center gap-1 ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
          {isPositive ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />}
          <span className="font-semibold">{Math.abs(change)}%</span>
        </div>
        <span className="text-sm text-muted-foreground">{timeframe}</span>
      </div>
      {clickable && <p className="mt-3 text-xs text-muted-foreground">Click to expand details</p>}
    </button>
  );
}
