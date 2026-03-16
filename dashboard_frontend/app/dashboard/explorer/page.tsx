'use client';

import { useEffect, useState } from 'react';
import { useProfile } from '@/lib/profiles';
import { DataTable } from '@/components/DataTable';

const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';

export default function ExplorerPage() {
  const { profileDef } = useProfile();
  const [data, setData] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [dataQuality, setDataQuality] = useState<any>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/dashboard?user_id=demo-user&date_range=last-90-days`, { cache: 'no-store' })
        .then(r => r.ok ? r.json() : { records: [] }),
      fetch(`${API}/analytics/data-quality?client_id=1`).then(r => r.json()),
    ]).then(([dashboard, quality]) => {
      setData(dashboard.records ?? []);
      setDataQuality(quality);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const EXPLORER_COLUMNS = [
    'date', 'channel', 'user', 'type', 'language', 'platform',
    'status', 'processedVideos', 'publishedVideos',
  ];

  return (
    <div style={{ minHeight: '100vh', background: 'var(--void)' }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-2.5" style={{ borderBottom: '1px solid var(--wire)' }}>
        <span className="section-id">Video Explorer</span>
        <div className="flex-1" />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.55rem', color: 'var(--on-low)' }}>
          {profileDef.displayName}
        </span>
      </div>

      {/* Data quality summary bar */}
      {dataQuality && (
        <div className="flex items-center gap-6 px-6 py-2 flex-wrap" style={{ borderBottom: '1px solid var(--wire)', background: 'var(--surface)' }}>
          <span style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.14em', color: 'var(--on-low)', textTransform: 'uppercase' }}>
            Data Quality
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-mid)' }}>
            {dataQuality.total_records?.toLocaleString()} records
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-mid)' }}>
            {dataQuality.distinct_videos?.toLocaleString()} unique videos
          </span>
          {dataQuality.duplicate_video_ids > 0 && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--warn)' }}>
              {dataQuality.duplicate_video_ids} potential duplicates
            </span>
          )}
          {dataQuality.null_publish_urls_on_published > 0 && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--signal)' }}>
              {dataQuality.null_publish_urls_on_published} missing publish URLs
            </span>
          )}

          {/* Field completeness chips */}
          <div className="flex-1" />
          {Object.entries(dataQuality.missing_by_field ?? {}).map(([field, info]: [string, any]) => (
            <span
              key={field}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.5rem',
                background: info.pct > 10 ? 'var(--signal-dim)' : 'var(--surface-raise)',
                color: info.pct > 10 ? 'var(--signal)' : 'var(--on-low)',
                padding: '1px 5px',
              }}
            >
              {field}: {info.pct}% null
            </span>
          ))}
        </div>
      )}

      {loading ? (
        <div className="px-6 py-8"><div className="scan-loader" /></div>
      ) : (
        <div style={{ padding: '24px 28px' }}>
          <DataTable
            data={data}
            columns={EXPLORER_COLUMNS}
            pageSize={50}
            searchable
            exportable
            title="Video Records"
          />
        </div>
      )}
    </div>
  );
}
