'use client';

import { useMemo, useState } from 'react';

interface DataTableProps {
  data: Record<string, unknown>[];
  columns?: string[];
  pageSize?: number;
  searchable?: boolean;
  exportable?: boolean;
  title?: string;
}

export function DataTable({ data, columns: propColumns, pageSize = 50, searchable = true, exportable = true, title }: DataTableProps) {
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(0);

  const columns = useMemo(() => propColumns ?? (data.length > 0 ? Object.keys(data[0]) : []), [data, propColumns]);

  const filtered = useMemo(() => {
    if (!search) return data;
    const q = search.toLowerCase();
    return data.filter((row) =>
      columns.some((col) => String(row[col] ?? '').toLowerCase().includes(q))
    );
  }, [data, search, columns]);

  const sorted = useMemo(() => {
    if (!sortKey) return filtered;
    return [...filtered].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [filtered, sortKey, sortDir]);

  const totalPages = Math.ceil(sorted.length / pageSize);
  const pageData = sorted.slice(page * pageSize, (page + 1) * pageSize);

  const handleSort = (col: string) => {
    if (sortKey === col) {
      setSortDir((d) => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(col);
      setSortDir('asc');
    }
  };

  const exportCSV = () => {
    const header = columns.join(',');
    const rows = sorted.map((row) =>
      columns.map((col) => {
        const v = String(row[col] ?? '');
        return v.includes(',') || v.includes('"') ? `"${v.replace(/"/g, '""')}"` : v;
      }).join(',')
    );
    const csv = [header, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title ?? 'export'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      {/* Header row */}
      <div className="flex items-center gap-4 mb-3 flex-wrap">
        {title && <span className="section-id">{title}</span>}
        <div className="flex-1" />
        {searchable && (
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            placeholder="Search..."
            style={{
              background: 'var(--surface-hi)',
              border: '1px solid var(--wire)',
              color: 'var(--on)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.65rem',
              padding: '4px 10px',
              outline: 'none',
              width: '200px',
            }}
          />
        )}
        {exportable && (
          <span className="action-text" onClick={exportCSV}>CSV ↓</span>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--wire-mid)' }}>
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => handleSort(col)}
                  style={{
                    padding: '6px 8px',
                    fontFamily: 'var(--font-condensed)',
                    fontSize: '0.55rem',
                    fontWeight: 700,
                    letterSpacing: '0.14em',
                    textTransform: 'uppercase',
                    color: sortKey === col ? 'var(--on)' : 'var(--on-low)',
                    textAlign: 'left',
                    cursor: 'pointer',
                    userSelect: 'none',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {col.replace(/_/g, ' ')}
                  {sortKey === col && (
                    <span style={{ marginLeft: '4px', fontSize: '0.5rem' }}>
                      {sortDir === 'asc' ? '▲' : '▼'}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageData.map((row, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--wire)' }}>
                {columns.map((col) => (
                  <td key={col} style={{
                    padding: '5px 8px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.65rem',
                    color: 'var(--on-mid)',
                    whiteSpace: 'nowrap',
                    maxWidth: '200px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}>
                    {String(row[col] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center gap-4 mt-3">
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
          {sorted.length.toLocaleString()} rows
        </span>
        <div className="flex-1" />
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <span
              className="action-text"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              style={{ opacity: page === 0 ? 0.3 : 1 }}
            >
              ← PREV
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
              {page + 1} / {totalPages}
            </span>
            <span
              className="action-text"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              style={{ opacity: page >= totalPages - 1 ? 0.3 : 1 }}
            >
              NEXT →
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
