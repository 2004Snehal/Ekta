'use client';

interface DimensionPickerProps {
  dim1: string;
  dim2: string | null;
  metric: string;
  onDim1Change: (dim: string) => void;
  onDim2Change: (dim: string | null) => void;
  onMetricChange: (metric: string) => void;
}

const DIMENSIONS = [
  { value: 'channel', label: 'Channel' },
  { value: 'user', label: 'User' },
  { value: 'language', label: 'Language' },
  { value: 'input_type', label: 'Input Type' },
  { value: 'output_type', label: 'Output Type' },
  { value: 'platform', label: 'Platform' },
];

const METRICS = [
  { value: 'count', label: 'Video Count' },
  { value: 'duration', label: 'Duration (hrs)' },
  { value: 'published_count', label: 'Published Count' },
  { value: 'publish_rate', label: 'Publish Rate %' },
];

export function DimensionPicker({ dim1, dim2, metric, onDim1Change, onDim2Change, onMetricChange }: DimensionPickerProps) {
  return (
    <div
      className="flex items-center gap-6 px-6 py-3 flex-wrap"
      style={{ borderBottom: '1px solid var(--wire)', background: 'var(--void)' }}
    >
      {/* Dim 1 */}
      <div className="flex flex-col gap-1.5">
        <span style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '0.65rem',
          fontWeight: 700,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: 'var(--on-low)',
        }}>
          Dimension 1
        </span>
        <select className="bare-select" value={dim1} onChange={(e) => onDim1Change(e.target.value)}>
          {DIMENSIONS.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>
      </div>

      <span style={{ color: 'var(--on-low)', fontSize: '0.85rem', alignSelf: 'flex-end', paddingBottom: '5px' }}>×</span>

      {/* Dim 2 */}
      <div className="flex flex-col gap-1.5">
        <span style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '0.65rem',
          fontWeight: 700,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: 'var(--on-low)',
        }}>
          Dimension 2
        </span>
        <select
          className="bare-select"
          value={dim2 ?? ''}
          onChange={(e) => onDim2Change(e.target.value || null)}
        >
          <option value="">None</option>
          {DIMENSIONS.filter((d) => d.value !== dim1).map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>
      </div>

      <div className="wire-v" style={{ height: '32px', alignSelf: 'flex-end', marginBottom: '4px' }} />

      {/* Metric */}
      <div className="flex flex-col gap-1.5">
        <span style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '0.65rem',
          fontWeight: 700,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: 'var(--on-low)',
        }}>
          Metric
        </span>
        <select className="bare-select" value={metric} onChange={(e) => onMetricChange(e.target.value)}>
          {METRICS.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
