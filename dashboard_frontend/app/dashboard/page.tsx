'use client';

import { useState } from 'react';
import { KPICard } from '@/components/KPICard';
import { ChartRenderer } from '@/components/ChartRenderer';
import { Filters } from '@/components/Filters';
import { InsightPanel } from '@/components/InsightPanel';
import { BarChart3, Video, Zap, TrendingUp } from 'lucide-react';

// Mock data for demonstration
const mockCharts = [
  {
    chart_type: 'line' as const,
    title: 'Processing Trend (Last 30 Days)',
    data: [
      { date: 'Day 1', processed: 125, uploaded: 98 },
      { date: 'Day 2', processed: 203, uploaded: 156 },
      { date: 'Day 3', processed: 287, uploaded: 212 },
      { date: 'Day 4', processed: 342, uploaded: 298 },
      { date: 'Day 5', processed: 401, uploaded: 345 },
      { date: 'Day 6', processed: 523, uploaded: 456 },
      { date: 'Day 7', processed: 612, uploaded: 534 },
      { date: 'Day 8', processed: 698, uploaded: 612 },
      { date: 'Day 9', processed: 745, uploaded: 687 },
      { date: 'Day 10', processed: 823, uploaded: 734 },
    ],
    x: 'date',
    y: 'processed',
    yAxis: 'processed',
  },
  {
    chart_type: 'bar' as const,
    title: 'Channel Performance',
    data: [
      { channel: 'YouTube', videos: 245, engagement: 8900 },
      { channel: 'TikTok', videos: 312, engagement: 12400 },
      { channel: 'Instagram', videos: 187, engagement: 7200 },
      { channel: 'LinkedIn', videos: 94, engagement: 3400 },
    ],
    x: 'channel',
    y: 'videos',
    yAxis: 'videos',
  },
  {
    chart_type: 'pie' as const,
    title: 'Output Distribution',
    data: [
      { name: 'Shorts', value: 45 },
      { name: 'Long-form', value: 28 },
      { name: 'Reels', value: 18 },
      { name: 'Stories', value: 9 },
    ],
    x: 'name',
    y: 'value',
    yAxis: 'value',
  },
  {
    chart_type: 'bar' as const,
    title: 'Publishing Funnel',
    data: [
      { stage: 'Uploaded', count: 1250, percent: 100 },
      { stage: 'Processed', count: 1089, percent: 87 },
      { stage: 'Published', count: 987, percent: 79 },
      { stage: 'Promoted', count: 654, percent: 52 },
    ],
    x: 'stage',
    y: 'count',
    yAxis: 'count',
  },
];

const mockInsights = [
  {
    title: 'Peak Performance Window',
    description: 'Videos published on weekdays at 9 AM - 11 AM generate 34% higher engagement on average.',
    actionable: true,
  },
  {
    title: 'Channel Recommendation',
    description: 'TikTok shows 38% higher audience growth this month. Consider allocating more resources here.',
    actionable: true,
  },
  {
    title: 'Processing Optimization',
    description: 'Your average processing time improved by 12% week-over-week. Current avg: 2.3 minutes per video.',
    actionable: false,
  },
  {
    title: 'Content Gap Identified',
    description: 'Tutorials and Behind-the-scenes content underperform. Educational content shows +45% potential.',
    actionable: true,
  },
];

export default function Dashboard() {
  const [filters, setFilters] = useState({});

  return (
    <div className="p-8 min-h-screen">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-foreground mb-2">Analytics Dashboard</h1>
        <p className="text-muted-foreground">Real-time insights into your video processing and publishing performance</p>
      </div>

      {/* Filters */}
      <Filters onApply={setFilters} />

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KPICard
          title="Uploaded Videos"
          value="1,245"
          change={12}
          timeframe="vs last week"
          icon={<Video className="w-5 h-5" />}
        />
        <KPICard
          title="Processed Videos"
          value="1,087"
          change={8}
          timeframe="vs last week"
          icon={<Zap className="w-5 h-5" />}
        />
        <KPICard
          title="Published Videos"
          value="987"
          change={15}
          timeframe="vs last week"
          icon={<TrendingUp className="w-5 h-5" />}
        />
        <KPICard
          title="Publish Rate"
          value="79%"
          change={-3}
          timeframe="vs last week"
          icon={<BarChart3 className="w-5 h-5" />}
        />
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {mockCharts.slice(0, 2).map((chart, idx) => (
          <ChartRenderer key={idx} chart={chart} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {mockCharts.slice(2, 4).map((chart, idx) => (
          <ChartRenderer key={idx + 2} chart={chart} />
        ))}
      </div>

      {/* Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <InsightPanel insights={mockInsights.slice(0, 2)} />
        <InsightPanel insights={mockInsights.slice(2, 4)} />
      </div>
    </div>
  );
}
