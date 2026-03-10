'use client';

import { ArrowUp, ArrowDown, TrendingUp } from 'lucide-react';

interface KPICardProps {
  title: string;
  value: string | number;
  change: number;
  timeframe: string;
  icon?: React.ReactNode;
}

export function KPICard({ title, value, change, timeframe, icon }: KPICardProps) {
  const isPositive = change >= 0;

  return (
    <div className="bg-card border border-border rounded-lg p-6 hover:border-primary/50 transition-all duration-300 hover:shadow-lg hover:shadow-primary/10">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-muted-foreground text-sm font-medium">{title}</p>
          <h3 className="text-3xl font-bold text-foreground mt-2">{value}</h3>
        </div>
        <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center text-primary">
          {icon || <TrendingUp className="w-5 h-5" />}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className={`flex items-center gap-1 ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
          {isPositive ? <ArrowUp className="w-4 h-4" /> : <ArrowDown className="w-4 h-4" />}
          <span className="font-semibold">{Math.abs(change)}%</span>
        </div>
        <span className="text-muted-foreground text-sm">{timeframe}</span>
      </div>
    </div>
  );
}
