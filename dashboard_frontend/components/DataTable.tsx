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
      <div className="flex items-center gap-4 mb-4 flex-wrap">
        {title && <span className="section-id">{title}</span>}
        <div className="flex-1" />
        {searchable && (
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            placeholder="Search…"
            style={{
              background: 'var(--surface)',
              border: '1.5px solid var(--wire)',
              color: 'var(--on)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem',
              padding: '6px 12px',
              outline: 'none',
              width: '220px',
              borderRadius: '8px',
              transition: 'border-color 0.2s',
            }}
            onFocus={(e) => { e.target.style.borderColor = 'var(--signal)'; }}
            onBlur={(e) => { e.target.style.borderColor = 'var(--wire)'; }}
          />
        )}
        {exportable && (
          <button
            className="action-text"
            onClick={exportCSV}
            style={{
              background: 'var(--surface-raise)',
              border: '1px solid var(--wire)',
              padding: '5px 12px',
              borderRadius: '8px',
              cursor: 'pointer',
            }}
          >
            CSV ↓
          </button>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto" style={{ borderRadius: '12px', border: '1px solid var(--wire)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--surface-hi)', borderBottom: '1.5px solid var(--wire)' }}>
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => handleSort(col)}
                  style={{
                    padding: '9px 12px',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    color: sortKey === col ? 'var(--signal)' : 'var(--on-low)',
                    textAlign: 'left',
                    cursor: 'pointer',
                    userSelect: 'none',
                    whiteSpace: 'nowrap',
                    letterSpacing: '0.02em',
                  }}
                >
                  {col.replace(/_/g, ' ')}
                  {sortKey === col && (
                    <span style={{ marginLeft: '5px', fontSize: '0.55rem' }}>
                      {sortDir === 'asc' ? '▲' : '▼'}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageData.map((row, i) => (
              <tr
                key={i}
                style={{
                  borderBottom: '1px solid var(--wire)',
                  background: i % 2 === 0 ? 'var(--surface)' : 'var(--surface-hi)',
                  transition: 'background 0.15s',
                }}
              >
                {columns.map((col) => (
                  <td key={col} style={{
                    padding: '7px 12px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.72rem',
                    color: 'var(--on-mid)',
                    whiteSpace: 'nowrap',
                    maxWidth: '200px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}>
                    {String(row[col] ?? '\u2014')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center gap-4 mt-4">
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--on-low)' }}>
          {sorted.length.toLocaleString()} rows
        </span>
        <div className="flex-1" />
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <button
              className="action-text"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              style={{
                opacity: page === 0 ? 0.3 : 1,
                background: 'var(--surface-raise)',
                border: '1px solid var(--wire)',
                padding: '4px 12px',
                borderRadius: '8px',
                cursor: page === 0 ? 'not-allowed' : 'pointer',
              }}
            >
              ← Prev
            </button>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--on-low)', minWidth: '70px', textAlign: 'center' }}>
              {page + 1} / {totalPages}
            </span>
            <button
              className="action-text"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              style={{
                opacity: page >= totalPages - 1 ? 0.3 : 1,
                background: 'var(--surface-raise)',
                border: '1px solid var(--wire)',
                padding: '4px 12px',
                borderRadius: '8px',
                cursor: page >= totalPages - 1 ? 'not-allowed' : 'pointer',
              }}
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
