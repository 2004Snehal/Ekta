'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Upload, Trash2, AlertCircle, CheckCircle2,
  ChevronLeft, ChevronRight, Loader2, RefreshCw,
  Users, Database, Plus, UserCheck,
  Link2, Link2Off, FlaskConical, Edit3,
  ZoomIn, ZoomOut, Maximize2, X, Save,
  Columns3, Table2, Copy, Terminal,
} from 'lucide-react';

// ────────────────────────────────────────────────────────────────────────── //
// Types
// ────────────────────────────────────────────────────────────────────────── //

interface Column {
  name: string;
  type: string;
  nullable: boolean;
  has_default: boolean;
  is_pk: boolean;
}

interface TableInfo {
  name: string;
  columns: Column[];
  primary_keys: string[];
}

interface TableRow {
  [key: string]: string | number | boolean | null;
}

interface ColumnDef {
  name: string;
  type: string;
  nullable: boolean;
  is_pk: boolean;
}

interface Relationship {
  constraint_name: string;
  from_table: string;
  from_column: string;
  to_table: string;
  to_column: string;
  link_type: 'fk' | 'logical';
}

interface User {
  user_id: string;
  email: string;
  role: string;
  user_profile: string;
  created_at: string | null;
}

type StatusState =
  | { type: 'idle' }
  | { type: 'loading' }
  | { type: 'success'; message: string }
  | { type: 'error'; message: string };

type Tab = 'data' | 'lab' | 'users';
type LabSubTab = 'viz' | 'edit' | 'create' | 'columns' | 'links';

// ────────────────────────────────────────────────────────────────────────── //
// Constants
// ────────────────────────────────────────────────────────────────────────── //

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '');
const PAGE_SIZE = 50;

const PG_TYPES = [
  'TEXT', 'VARCHAR', 'INTEGER', 'BIGINT', 'NUMERIC', 'BOOLEAN',
  'TIMESTAMPTZ', 'TIMESTAMP', 'DATE', 'UUID', 'JSONB',
  'FLOAT', 'REAL', 'SMALLINT', 'SERIAL', 'BIGSERIAL',
];

function authHeaders(extra?: Record<string, string>): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  return token ? { Authorization: `Bearer ${token}`, ...extra } : { ...extra };
}

// ────────────────────────────────────────────────────────────────────────── //
// Page
// ────────────────────────────────────────────────────────────────────────── //

export default function AdminPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>('data');
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const raw = localStorage.getItem('auth_user');
    if (!raw) { router.replace('/signin'); return; }
    try {
      const user = JSON.parse(raw);
      if (user.role !== 'admin') { router.replace('/dashboard'); return; }
    } catch { router.replace('/signin'); return; }
    setAuthChecked(true);
  }, [router]);

  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-8 min-h-screen bg-background">
      <div className="max-w-7xl mx-auto">

        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground">Admin Console</h1>
          <p className="text-muted-foreground mt-1">
            Manage data schema, tables, and user profiles.
          </p>
        </div>

        <div className="flex gap-1 mb-6 bg-muted/30 p-1 rounded-xl w-fit">
          <TabButton active={activeTab === 'data'} onClick={() => setActiveTab('data')}>
            <Database className="w-4 h-4" />
            Data Management
          </TabButton>
          <TabButton active={activeTab === 'lab'} onClick={() => setActiveTab('lab')}>
            <FlaskConical className="w-4 h-4" />
            Data Lab
          </TabButton>
          <TabButton active={activeTab === 'users'} onClick={() => setActiveTab('users')}>
            <Users className="w-4 h-4" />
            User Management
          </TabButton>
        </div>

        {activeTab === 'data' && <DataTab />}
        {activeTab === 'lab' && <DataLabTab />}
        {activeTab === 'users' && <UsersTab />}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────── //
// Data Management Tab (original)
// ────────────────────────────────────────────────────────────────────────── //

function DataTab() {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string>('');
  const [tableInfo, setTableInfo] = useState<TableInfo | null>(null);
  const [rows, setRows] = useState<TableRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [selectedPks, setSelectedPks] = useState<Set<string | number>>(new Set());
  const [loadingTables, setLoadingTables] = useState(true);
  const [loadingRows, setLoadingRows] = useState(false);
  const [newTableName, setNewTableName] = useState('');
  const [newTableFile, setNewTableFile] = useState<File | null>(null);
  const [newTableStatus, setNewTableStatus] = useState<StatusState>({ type: 'idle' });
  const [newTableDrag, setNewTableDrag] = useState(false);
  const newTableInputRef = useRef<HTMLInputElement>(null);
  const [appendFile, setAppendFile] = useState<File | null>(null);
  const [appendDrag, setAppendDrag] = useState(false);
  const [appendStatus, setAppendStatus] = useState<StatusState>({ type: 'idle' });
  const appendInputRef = useRef<HTMLInputElement>(null);
  const [deleteStatus, setDeleteStatus] = useState<StatusState>({ type: 'idle' });
  const [dropStatus, setDropStatus] = useState<StatusState>({ type: 'idle' });

  const loadTables = useCallback(() => {
    setLoadingTables(true);
    fetch(`${API_BASE}/admin/tables`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => setTables(d.tables ?? []))
      .catch(() => setTables([]))
      .finally(() => setLoadingTables(false));
  }, []);

  useEffect(() => { loadTables(); }, [loadTables]);

  const loadRows = useCallback((tableName: string, currentPage: number) => {
    if (!tableName) return;
    setLoadingRows(true);
    fetch(
      `${API_BASE}/admin/table/${tableName}/rows?limit=${PAGE_SIZE}&offset=${currentPage * PAGE_SIZE}`,
      { headers: authHeaders() }
    )
      .then((r) => r.json())
      .then((d) => { setRows(d.rows ?? []); setTotal(d.total ?? 0); })
      .catch(() => setRows([]))
      .finally(() => setLoadingRows(false));
  }, []);

  useEffect(() => {
    if (!selectedTable) return;
    setTableInfo(tables.find((t) => t.name === selectedTable) ?? null);
    setSelectedPks(new Set());
    setDeleteStatus({ type: 'idle' });
    loadRows(selectedTable, page);
  }, [selectedTable, page, tables, loadRows]);

  function handleTableChange(name: string) {
    setSelectedTable(name); setPage(0); setRows([]); setTotal(0);
    setAppendFile(null); setAppendStatus({ type: 'idle' });
    setDeleteStatus({ type: 'idle' }); setDropStatus({ type: 'idle' });
  }

  const pkCol = tableInfo?.primary_keys[0] ?? null;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  function toggleRow(pk: string | number) {
    setSelectedPks((prev) => { const n = new Set(prev); n.has(pk) ? n.delete(pk) : n.add(pk); return n; });
  }
  function toggleAll() {
    if (!pkCol) return;
    const all = rows.map((r) => r[pkCol] as string | number);
    setSelectedPks(selectedPks.size === rows.length ? new Set() : new Set(all));
  }

  async function handleCreateTable() {
    if (!newTableFile || !newTableName.trim()) return;
    setNewTableStatus({ type: 'loading' });
    const form = new FormData();
    form.append('file', newTableFile);
    try {
      const res = await fetch(`${API_BASE}/admin/table/${newTableName.trim()}/upload-csv`, {
        method: 'POST', headers: authHeaders(), body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Failed');
      setNewTableStatus({ type: 'success', message: `Table '${data.table}' ${data.action} with ${data.inserted} rows.` });
      setNewTableFile(null); setNewTableName('');
      if (newTableInputRef.current) newTableInputRef.current.value = '';
      loadTables();
    } catch (e) { setNewTableStatus({ type: 'error', message: (e as Error).message }); }
  }

  async function handleAppend() {
    if (!appendFile || !selectedTable) return;
    setAppendStatus({ type: 'loading' });
    const form = new FormData();
    form.append('file', appendFile);
    try {
      const res = await fetch(`${API_BASE}/admin/table/${selectedTable}/append-csv`, {
        method: 'POST', headers: authHeaders(), body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Failed');
      setAppendStatus({ type: 'success', message: `Inserted ${data.inserted} rows into ${data.table}.` });
      setAppendFile(null);
      if (appendInputRef.current) appendInputRef.current.value = '';
      loadRows(selectedTable, page);
    } catch (e) { setAppendStatus({ type: 'error', message: (e as Error).message }); }
  }

  async function handleDeleteRows() {
    if (!pkCol || selectedPks.size === 0) return;
    setDeleteStatus({ type: 'loading' });
    try {
      const res = await fetch(`${API_BASE}/admin/table/${selectedTable}/rows`, {
        method: 'DELETE',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ primary_key_column: pkCol, values: Array.from(selectedPks) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Delete failed');
      setDeleteStatus({ type: 'success', message: `Deleted ${data.deleted} row(s).` });
      setSelectedPks(new Set());
      loadRows(selectedTable, page);
    } catch (e) { setDeleteStatus({ type: 'error', message: (e as Error).message }); }
  }

  async function handleDropTable() {
    if (!selectedTable) return;
    if (!window.confirm(`Permanently drop table '${selectedTable}'? This cannot be undone.`)) return;
    setDropStatus({ type: 'loading' });
    try {
      const res = await fetch(`${API_BASE}/admin/table/${selectedTable}`, {
        method: 'DELETE', headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Drop failed');
      setDropStatus({ type: 'success', message: `Table '${data.dropped}' dropped.` });
      setSelectedTable(''); setRows([]); loadTables();
    } catch (e) { setDropStatus({ type: 'error', message: (e as Error).message }); }
  }

  return (
    <div className="space-y-6">
      <div className="bg-card border border-border rounded-xl p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
          <StepBadge><Plus className="w-3 h-3" /></StepBadge>
          Create New Table from CSV
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          Drag and drop a CSV file to create a table. Columns are inferred as TEXT; an auto-increment{' '}
          <code className="text-xs bg-muted px-1 py-0.5 rounded">_row_id</code> primary key is added.
          For manual column definitions use the <strong>Data Lab</strong> tab.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 mb-3">
          <input
            type="text" value={newTableName}
            onChange={(e) => setNewTableName(e.target.value)}
            placeholder="table_name (letters, numbers, underscores)"
            className="flex-1 bg-background border border-border rounded-lg px-4 py-2.5 text-foreground focus:outline-none focus:ring-2 focus:ring-primary text-sm"
          />
        </div>
        <DropZone file={newTableFile} dragOver={newTableDrag} inputRef={newTableInputRef}
          onDragOver={() => setNewTableDrag(true)} onDragLeave={() => setNewTableDrag(false)}
          onDrop={(f) => { setNewTableFile(f); setNewTableDrag(false); setNewTableStatus({ type: 'idle' }); }}
          onChange={(f) => { setNewTableFile(f); setNewTableStatus({ type: 'idle' }); }} />
        <StatusBanner status={newTableStatus} className="mt-3" />
        <div className="mt-4 flex items-center gap-3">
          <button onClick={handleCreateTable}
            disabled={!newTableFile || !newTableName.trim() || newTableStatus.type === 'loading'}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-2.5 rounded-lg font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed text-sm">
            {newTableStatus.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            {newTableStatus.type === 'loading' ? 'Creating…' : 'Create Table'}
          </button>
          {newTableFile && newTableStatus.type !== 'loading' && (
            <button onClick={() => { setNewTableFile(null); setNewTableStatus({ type: 'idle' }); if (newTableInputRef.current) newTableInputRef.current.value = ''; }}
              className="text-sm text-muted-foreground hover:text-foreground">Clear</button>
          )}
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
          <StepBadge><Database className="w-3 h-3" /></StepBadge>
          Manage Existing Table
        </h2>
        {loadingTables ? (
          <span className="flex items-center gap-2 text-muted-foreground text-sm"><Loader2 className="w-4 h-4 animate-spin" />Loading tables…</span>
        ) : (
          <div className="flex items-center gap-3">
            <select value={selectedTable} onChange={(e) => handleTableChange(e.target.value)}
              className="w-full max-w-sm bg-background border border-border rounded-lg px-4 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-primary text-sm">
              <option value="">— choose a table —</option>
              {tables.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
            </select>
            {selectedTable && (
              <button onClick={handleDropTable} disabled={dropStatus.type === 'loading'}
                className="flex items-center gap-2 bg-destructive/10 text-destructive border border-destructive/30 px-4 py-2 rounded-lg text-sm font-medium hover:bg-destructive/20 disabled:opacity-50">
                {dropStatus.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                Drop Table
              </button>
            )}
          </div>
        )}
        <StatusBanner status={dropStatus} className="mt-3" />
      </div>

      {selectedTable && tableInfo && (
        <>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="p-6 border-b border-border flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-foreground">
                Table Data
                <span className="text-sm font-normal text-muted-foreground ml-2">— {total.toLocaleString()} row{total !== 1 ? 's' : ''}</span>
              </h2>
              <div className="flex items-center gap-2">
                <button onClick={() => loadRows(selectedTable, page)}
                  className="p-2 rounded-lg border border-border hover:bg-muted text-muted-foreground" title="Refresh">
                  <RefreshCw className="w-4 h-4" />
                </button>
                {selectedPks.size > 0 && (
                  <button onClick={handleDeleteRows} disabled={deleteStatus.type === 'loading'}
                    className="flex items-center gap-2 bg-destructive text-destructive-foreground px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
                    {deleteStatus.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                    Delete {selectedPks.size} selected
                  </button>
                )}
              </div>
            </div>
            <StatusBanner status={deleteStatus} className="mx-6 mt-4" />
            <div className="overflow-x-auto">
              {loadingRows ? (
                <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground"><Loader2 className="w-5 h-5 animate-spin" /> Loading rows…</div>
              ) : rows.length === 0 ? (
                <div className="flex items-center justify-center py-16 text-muted-foreground text-sm">No rows found.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 border-b border-border">
                    <tr>
                      {pkCol && <th className="px-4 py-3 w-10"><input type="checkbox" checked={selectedPks.size === rows.length && rows.length > 0} onChange={toggleAll} className="rounded accent-primary" /></th>}
                      {tableInfo.columns.map((col) => (
                        <th key={col.name} className="px-4 py-3 text-left font-medium text-muted-foreground whitespace-nowrap">
                          {col.name}{col.is_pk && <span className="ml-1 text-xs text-primary">[PK]</span>}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {rows.map((row, i) => {
                      const pkVal = pkCol ? (row[pkCol] as string | number) : null;
                      const selected = pkVal !== null && pkVal !== undefined && selectedPks.has(pkVal);
                      return (
                        <tr key={i} className={selected ? 'bg-primary/10' : 'hover:bg-muted/30 transition-colors'}>
                          {pkCol && <td className="px-4 py-2"><input type="checkbox" checked={selected} onChange={() => pkVal !== null && pkVal !== undefined && toggleRow(pkVal)} className="rounded accent-primary" /></td>}
                          {tableInfo.columns.map((col) => (
                            <td key={col.name} className="px-4 py-2 text-foreground whitespace-nowrap max-w-[200px] truncate" title={row[col.name] != null ? String(row[col.name]) : ''}>
                              {row[col.name] == null ? <span className="text-muted-foreground italic text-xs">null</span> : String(row[col.name])}
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
            {total > PAGE_SIZE && (
              <div className="p-4 border-t border-border flex items-center justify-between">
                <span className="text-sm text-muted-foreground">{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total.toLocaleString()}</span>
                <div className="flex items-center gap-2">
                  <button onClick={() => setPage((p) => p - 1)} disabled={page === 0} className="p-1.5 rounded border border-border hover:bg-muted disabled:opacity-40"><ChevronLeft className="w-4 h-4" /></button>
                  <span className="text-sm px-2 text-foreground">{page + 1} / {totalPages}</span>
                  <button onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages - 1} className="p-1.5 rounded border border-border hover:bg-muted disabled:opacity-40"><ChevronRight className="w-4 h-4" /></button>
                </div>
              </div>
            )}
          </div>

          <div className="bg-card border border-border rounded-xl p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
              <StepBadge><Upload className="w-3 h-3" /></StepBadge>
              Append Rows to <code className="text-primary text-sm">{selectedTable}</code>
            </h2>
            <div className="mb-4">
              <p className="text-sm text-muted-foreground mb-2">CSV columns must match the table schema.</p>
              <div className="flex flex-wrap gap-2">
                {tableInfo.columns.map((col) => {
                  const isAuto = col.is_pk && col.has_default;
                  const isRequired = !col.nullable && !col.has_default && !isAuto;
                  return (
                    <span key={col.name} className={`text-xs px-2.5 py-1 rounded-md font-mono border ${isAuto ? 'bg-muted/20 border-border text-muted-foreground line-through opacity-60' : isRequired ? 'bg-primary/10 border-primary/40 text-primary' : 'bg-muted/30 border-border text-foreground'}`}>
                      {col.name}{isRequired && <span className="text-red-400 ml-0.5">*</span>}
                    </span>
                  );
                })}
              </div>
            </div>
            <DropZone file={appendFile} dragOver={appendDrag} inputRef={appendInputRef}
              onDragOver={() => setAppendDrag(true)} onDragLeave={() => setAppendDrag(false)}
              onDrop={(f) => { setAppendFile(f); setAppendDrag(false); setAppendStatus({ type: 'idle' }); }}
              onChange={(f) => { setAppendFile(f); setAppendStatus({ type: 'idle' }); }} />
            <StatusBanner status={appendStatus} className="mt-3" />
            <div className="mt-4 flex items-center gap-3">
              <button onClick={handleAppend} disabled={!appendFile || appendStatus.type === 'loading'}
                className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-2.5 rounded-lg font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed text-sm">
                {appendStatus.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                {appendStatus.type === 'loading' ? 'Uploading…' : 'Upload & Append'}
              </button>
              {appendFile && appendStatus.type !== 'loading' && (
                <button onClick={() => { setAppendFile(null); setAppendStatus({ type: 'idle' }); if (appendInputRef.current) appendInputRef.current.value = ''; }}
                  className="text-sm text-muted-foreground hover:text-foreground">Clear</button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────── //
// Data Lab Tab
// ────────────────────────────────────────────────────────────────────────── //

function DataLabTab() {
  const [labTab, setLabTab] = useState<LabSubTab>('viz');
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [loadingTables, setLoadingTables] = useState(true);

  const loadTables = useCallback(() => {
    setLoadingTables(true);
    fetch(`${API_BASE}/admin/tables`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => setTables(d.tables ?? []))
      .catch(() => setTables([]))
      .finally(() => setLoadingTables(false));
  }, []);

  const loadRelationships = useCallback(() => {
    fetch(`${API_BASE}/admin/schema/relationships`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => setRelationships(d.relationships ?? []))
      .catch(() => setRelationships([]));
  }, []);

  useEffect(() => { loadTables(); loadRelationships(); }, [loadTables, loadRelationships]);

  // Silent refresh: updates data without setting loadingTables=true, so panels
  // (AddColumnsPanel etc.) stay mounted and can show their own success/error state.
  const refresh = useCallback(() => {
    fetch(`${API_BASE}/admin/tables`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => setTables(d.tables ?? []))
      .catch(() => {});
    loadRelationships();
  }, [loadRelationships]);

  const labTabs: { id: LabSubTab; label: string; icon: React.ReactNode }[] = [
    { id: 'viz',     label: 'Schema Visualizer', icon: <Maximize2 className="w-4 h-4" /> },
    { id: 'edit',    label: 'Edit Data',         icon: <Edit3 className="w-4 h-4" /> },
    { id: 'create',  label: 'New Table',         icon: <Table2 className="w-4 h-4" /> },
    { id: 'columns', label: 'Add Columns',       icon: <Columns3 className="w-4 h-4" /> },
    { id: 'links',   label: 'Schema Links',      icon: <Link2 className="w-4 h-4" /> },
  ];

  return (
    <div className="space-y-5">
      <div className="bg-card border border-border rounded-xl p-1 flex gap-1 overflow-x-auto w-fit">
        {labTabs.map((t) => (
          <button key={t.id} onClick={() => setLabTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${labTab === t.id ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted/40'}`}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {loadingTables && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading schema…
        </div>
      )}

      {!loadingTables && (
        <>
          {labTab === 'viz'     && <SchemaVisualizerPanel tables={tables} relationships={relationships} />}
          {labTab === 'edit'    && <EditDataPanel tables={tables} relationships={relationships} onRefresh={refresh} onGoToLinks={() => setLabTab('links')} />}
          {labTab === 'create'  && <CreateTablePanel onCreated={refresh} />}
          {labTab === 'columns' && <AddColumnsPanel tables={tables} onAdded={refresh} />}
          {labTab === 'links'   && <SchemaLinksPanel tables={tables} relationships={relationships} onChanged={refresh} />}
        </>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────── //
// Schema Visualizer (ERD)
// ────────────────────────────────────────────────────────────────────────── //

const TABLE_W = 220;
const COL_H = 22;
const HEADER_H = 36;

function tableHeight(t: TableInfo) { return HEADER_H + t.columns.length * COL_H + 8; }

function SchemaVisualizerPanel({ tables, relationships }: { tables: TableInfo[]; relationships: Relationship[] }) {
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<{ table: string; startMx: number; startMy: number; origX: number; origY: number } | null>(null);
  const panRef = useRef<{ startMx: number; startMy: number; origPx: number; origPy: number } | null>(null);

  useEffect(() => {
    if (tables.length === 0) return;
    setPositions((prev) => {
      const next = { ...prev };
      const cols = Math.max(1, Math.ceil(Math.sqrt(tables.length)));
      tables.forEach((t, i) => {
        if (!next[t.name]) {
          next[t.name] = { x: (i % cols) * (TABLE_W + 60) + 60, y: Math.floor(i / cols) * 320 + 60 };
        }
      });
      return next;
    });
  }, [tables]);

  function resetLayout() {
    const cols = Math.max(1, Math.ceil(Math.sqrt(tables.length)));
    const next: Record<string, { x: number; y: number }> = {};
    tables.forEach((t, i) => {
      next[t.name] = { x: (i % cols) * (TABLE_W + 60) + 60, y: Math.floor(i / cols) * 320 + 60 };
    });
    setPositions(next);
    setScale(1);
    setPan({ x: 0, y: 0 });
  }

  function onTableMouseDown(e: React.MouseEvent, name: string) {
    e.stopPropagation();
    const pos = positions[name] ?? { x: 0, y: 0 };
    dragRef.current = { table: name, startMx: e.clientX, startMy: e.clientY, origX: pos.x, origY: pos.y };
  }

  function onSvgMouseDown(e: React.MouseEvent) {
    if (dragRef.current) return;
    panRef.current = { startMx: e.clientX, startMy: e.clientY, origPx: pan.x, origPy: pan.y };
  }

  function onSvgMouseMove(e: React.MouseEvent) {
    if (dragRef.current) {
      const dx = (e.clientX - dragRef.current.startMx) / scale;
      const dy = (e.clientY - dragRef.current.startMy) / scale;
      setPositions((prev) => ({ ...prev, [dragRef.current!.table]: { x: dragRef.current!.origX + dx, y: dragRef.current!.origY + dy } }));
    } else if (panRef.current) {
      const dx = (e.clientX - panRef.current.startMx) / scale;
      const dy = (e.clientY - panRef.current.startMy) / scale;
      setPan({ x: panRef.current.origPx + dx, y: panRef.current.origPy + dy });
    }
  }

  function onSvgMouseUp() { dragRef.current = null; panRef.current = null; }

  function onSvgWheel(e: React.WheelEvent) {
    e.preventDefault();
    setScale((s) => Math.max(0.3, Math.min(2.5, s * (e.deltaY > 0 ? 0.9 : 1.1))));
  }

  if (tables.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground">
        No tables in the data schema yet. Create some in the <strong>New Table</strong> tab.
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="p-4 border-b border-border flex items-center justify-between">
        <h2 className="font-semibold text-foreground flex items-center gap-2">
          <Maximize2 className="w-4 h-4" /> Schema Visualizer
          <span className="text-xs text-muted-foreground font-normal ml-1">
            — {tables.length} table{tables.length !== 1 ? 's' : ''}, {relationships.length} link{relationships.length !== 1 ? 's' : ''}
          </span>
        </h2>
        <div className="flex items-center gap-2">
          <button onClick={() => setScale((s) => Math.min(2.5, s * 1.2))} className="p-1.5 rounded border border-border hover:bg-muted text-muted-foreground"><ZoomIn className="w-4 h-4" /></button>
          <button onClick={() => setScale((s) => Math.max(0.3, s * 0.8))} className="p-1.5 rounded border border-border hover:bg-muted text-muted-foreground"><ZoomOut className="w-4 h-4" /></button>
          <button onClick={resetLayout} className="p-1.5 rounded border border-border hover:bg-muted text-muted-foreground text-xs px-3">Reset</button>
          <span className="text-xs text-muted-foreground">{Math.round(scale * 100)}%</span>
        </div>
      </div>

      <svg
        ref={svgRef}
        className="w-full bg-muted/10 cursor-grab active:cursor-grabbing"
        style={{ height: 520, userSelect: 'none' }}
        onMouseDown={onSvgMouseDown}
        onMouseMove={onSvgMouseMove}
        onMouseUp={onSvgMouseUp}
        onMouseLeave={onSvgMouseUp}
        onWheel={onSvgWheel}
      >
        <g transform={`scale(${scale}) translate(${pan.x},${pan.y})`}>
          {/* FK / link arrows */}
          {relationships.map((rel) => {
            const fp = positions[rel.from_table];
            const tp = positions[rel.to_table];
            if (!fp || !tp) return null;
            const ft = tables.find((t) => t.name === rel.from_table);
            const tt = tables.find((t) => t.name === rel.to_table);
            if (!ft || !tt) return null;
            const fromColIdx = ft.columns.findIndex((c) => c.name === rel.from_column);
            const toColIdx = tt.columns.findIndex((c) => c.name === rel.to_column);
            const x1 = fp.x + TABLE_W;
            const y1 = fp.y + HEADER_H + fromColIdx * COL_H + COL_H / 2;
            const x2 = tp.x;
            const y2 = tp.y + HEADER_H + toColIdx * COL_H + COL_H / 2;
            const mx = (x1 + x2) / 2;
            const isHov = hovered === rel.from_table || hovered === rel.to_table;
            const color = rel.link_type === 'fk' ? '#6366f1' : '#f59e0b';
            return (
              <g key={rel.constraint_name}>
                <path d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
                  fill="none" stroke={color} strokeWidth={isHov ? 2 : 1.5}
                  strokeDasharray={rel.link_type === 'logical' ? '6,3' : undefined}
                  opacity={isHov ? 1 : 0.6} />
                <circle cx={x1} cy={y1} r={3} fill={color} opacity={isHov ? 1 : 0.7} />
                <circle cx={x2} cy={y2} r={3} fill={color} opacity={isHov ? 1 : 0.7} />
              </g>
            );
          })}

          {/* Table boxes */}
          {tables.map((tbl) => {
            const pos = positions[tbl.name];
            if (!pos) return null;
            const h = tableHeight(tbl);
            const isHov = hovered === tbl.name;
            return (
              <g key={tbl.name} transform={`translate(${pos.x},${pos.y})`}
                onMouseDown={(e) => onTableMouseDown(e, tbl.name)}
                onMouseEnter={() => setHovered(tbl.name)}
                onMouseLeave={() => setHovered(null)}
                style={{ cursor: 'move' }}>
                <rect x={0} y={0} width={TABLE_W} height={h} rx={8}
                  fill={isHov ? 'rgba(99,102,241,0.07)' : 'rgba(30,30,40,0.95)'}
                  stroke={isHov ? '#6366f1' : '#3f3f46'} strokeWidth={isHov ? 1.5 : 1} />
                {/* Header */}
                <rect x={0} y={0} width={TABLE_W} height={HEADER_H} rx={8} fill="#1e1e2e" />
                <rect x={0} y={16} width={TABLE_W} height={20} fill="#1e1e2e" />
                <text x={12} y={22} fontSize={12} fontWeight="700" fill="#e4e4f0"
                  style={{ fontFamily: 'monospace' }}>{tbl.name}</text>
                <text x={TABLE_W - 10} y={22} fontSize={9} fill="#6366f1" textAnchor="end">
                  {tbl.columns.length} cols
                </text>
                {/* Columns */}
                {tbl.columns.map((col, ci) => {
                  const cy = HEADER_H + ci * COL_H + 4;
                  const isPk = tbl.primary_keys.includes(col.name);
                  const isFk = relationships.some(
                    (r) => (r.from_table === tbl.name && r.from_column === col.name) ||
                            (r.to_table === tbl.name && r.to_column === col.name)
                  );
                  const dotColor = isPk ? '#facc15' : isFk ? '#818cf8' : '#52525b';
                  return (
                    <g key={col.name}>
                      <circle cx={14} cy={cy + COL_H / 2} r={4} fill={dotColor} />
                      <text x={24} y={cy + COL_H / 2 + 4} fontSize={11} fill={isPk ? '#facc15' : '#d4d4d8'}
                        style={{ fontFamily: 'monospace' }}>
                        {col.name.length > 18 ? col.name.slice(0, 17) + '…' : col.name}
                      </text>
                      <text x={TABLE_W - 8} y={cy + COL_H / 2 + 4} fontSize={9} fill="#52525b" textAnchor="end">
                        {col.type.toLowerCase()}
                      </text>
                    </g>
                  );
                })}
              </g>
            );
          })}
        </g>
      </svg>

      <div className="px-4 py-2 border-t border-border flex items-center gap-5 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 rounded bg-indigo-500 inline-block" />FK constraint</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 rounded border-t-2 border-amber-400 border-dashed inline-block" />Logical link</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-yellow-400 inline-block" />Primary key</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-indigo-400 inline-block" />Link column</span>
        <span className="ml-auto text-muted-foreground/60">Drag to reposition · Scroll to zoom · Middle-drag to pan</span>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────── //
// Edit Data Panel — cascade is FULLY driven by defined Schema Links
// The join column is NEVER manually picked: it comes from the relationship.
// ────────────────────────────────────────────────────────────────────────── //

interface EditModal {
  row: TableRow;
  col: string;
  currentValue: string;
}

/**
 * One "cascade group" per unique join-column found in the defined relationships.
 * E.g. if ACD.C → ABC.C then: { joinCol:'c', joinValue:'key1', targets:[{table:'abc',toCol:'c'}] }
 */
interface CascadeGroup {
  joinCol: string;
  joinValue: string | number | null;
  targets: { table: string; toCol: string; linkType: 'fk' | 'logical' }[];
}

function EditDataPanel({
  tables, relationships, onRefresh, onGoToLinks,
}: {
  tables: TableInfo[];
  relationships: Relationship[];
  onRefresh: () => void;
  onGoToLinks: () => void;
}) {
  const [selectedTable, setSelectedTable] = useState('');
  const [tableInfo, setTableInfo] = useState<TableInfo | null>(null);
  const [rows, setRows] = useState<TableRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loadingRows, setLoadingRows] = useState(false);

  const [editModal, setEditModal] = useState<EditModal | null>(null);
  const [editValue, setEditValue] = useState('');
  const [cascadeOn, setCascadeOn] = useState(true);
  // Derived from defined relationships — NOT manually chosen by user
  const [cascadeGroups, setCascadeGroups] = useState<CascadeGroup[]>([]);
  const [updateStatus, setUpdateStatus] = useState<StatusState>({ type: 'idle' });

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const loadRows = useCallback((tableName: string, pg: number) => {
    if (!tableName) return;
    setLoadingRows(true);
    fetch(`${API_BASE}/admin/table/${tableName}/rows?limit=${PAGE_SIZE}&offset=${pg * PAGE_SIZE}`, {
      headers: authHeaders(),
    })
      .then((r) => r.json())
      .then((d) => { setRows(d.rows ?? []); setTotal(d.total ?? 0); })
      .catch(() => setRows([]))
      .finally(() => setLoadingRows(false));
  }, []);

  useEffect(() => {
    const info = tables.find((t) => t.name === selectedTable) ?? null;
    setTableInfo(info);
    if (selectedTable) loadRows(selectedTable, 0);
    setPage(0);
  }, [selectedTable, tables, loadRows]);

  useEffect(() => {
    if (selectedTable) loadRows(selectedTable, page);
  }, [page, selectedTable, loadRows]);

  /**
   * Build cascade groups from the pre-defined relationships.
   * Group by the join column used in THIS table so each group becomes one API call.
   */
  function buildCascadeGroups(row: TableRow): CascadeGroup[] {
    const groups: Record<string, CascadeGroup> = {};
    for (const rel of relationships) {
      let myJoinCol: string | null = null;
      let theirTable: string | null = null;
      let theirCol: string | null = null;

      if (rel.from_table === selectedTable) {
        myJoinCol = rel.from_column;
        theirTable = rel.to_table;
        theirCol = rel.to_column;
      } else if (rel.to_table === selectedTable) {
        myJoinCol = rel.to_column;
        theirTable = rel.from_table;
        theirCol = rel.from_column;
      }
      if (!myJoinCol || !theirTable || !theirCol) continue;

      if (!groups[myJoinCol]) {
        groups[myJoinCol] = {
          joinCol: myJoinCol,
          joinValue: row[myJoinCol] ?? null,
          targets: [],
        };
      }
      groups[myJoinCol].targets.push({
        table: theirTable,
        toCol: theirCol,
        linkType: rel.link_type,
      });
    }
    return Object.values(groups);
  }

  function openEdit(row: TableRow, col: string) {
    const val = row[col];
    setEditModal({ row, col, currentValue: val == null ? '' : String(val) });
    setEditValue(val == null ? '' : String(val));
    setCascadeOn(true);
    setUpdateStatus({ type: 'idle' });
    setCascadeGroups(buildCascadeGroups(row));
  }

  async function handleSaveEdit() {
    if (!editModal || !tableInfo) return;
    setUpdateStatus({ type: 'loading' });

    try {
      const allCascaded: { table: string; rows_updated: number }[] = [];
      let totalUpdated = 0;

      if (!cascadeOn || cascadeGroups.length === 0) {
        // No relationships defined — update only this table, identify row by PK
        const pkCol = tableInfo.primary_keys[0] ?? tableInfo.columns[0]?.name;
        const res = await fetch(`${API_BASE}/admin/table/${selectedTable}/update-cell`, {
          method: 'PATCH',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            join_column: pkCol,
            join_value: editModal.row[pkCol],
            target_column: editModal.col,
            new_value: editValue,
            cascade: false,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail ?? 'Update failed');
        totalUpdated = data.rows_updated;
      } else {
        // One API call per join-column group (each group = one relationship axis)
        for (const group of cascadeGroups) {
          const res = await fetch(`${API_BASE}/admin/table/${selectedTable}/update-cell`, {
            method: 'PATCH',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({
              join_column: group.joinCol,      // ← from Schema Links, NOT user-picked
              join_value: group.joinValue,     // ← this row's value for that join column
              target_column: editModal.col,
              new_value: editValue,
              cascade: true,
            }),
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail ?? 'Update failed');
          totalUpdated = Math.max(totalUpdated, data.rows_updated);
          allCascaded.push(...(data.cascaded ?? []));
        }
      }

      const cascadeSummary = allCascaded.length
        ? ` Cascaded to: ${allCascaded.map((c) => `${c.table} (${c.rows_updated} row${c.rows_updated !== 1 ? 's' : ''})`).join(', ')}.`
        : '';
      setUpdateStatus({ type: 'success', message: `Updated ${totalUpdated} row(s) in ${selectedTable}.${cascadeSummary}` });
      loadRows(selectedTable, page);
      onRefresh();
      setTimeout(() => setEditModal(null), 2000);
    } catch (e) {
      setUpdateStatus({ type: 'error', message: (e as Error).message });
    }
  }

  // Which columns in this table are join keys (for header label)
  const linkedCols = new Set(
    relationships
      .filter((r) => r.from_table === selectedTable || r.to_table === selectedTable)
      .map((r) => r.from_table === selectedTable ? r.from_column : r.to_column)
  );

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="font-semibold text-foreground mb-3 flex items-center gap-2">
          <Edit3 className="w-4 h-4" /> Edit Table Data
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          Click any cell to edit. Cascade targets are determined automatically from the relationships
          you defined in <button onClick={onGoToLinks} className="text-primary underline hover:no-underline">Schema Links</button> — the join column is never guessed.
        </p>
        <div className="flex items-center gap-3">
          <select value={selectedTable} onChange={(e) => setSelectedTable(e.target.value)}
            className="w-full max-w-xs bg-background border border-border rounded-lg px-4 py-2 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary">
            <option value="">— select a table —</option>
            {tables.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
          </select>
          {selectedTable && (
            <button onClick={() => loadRows(selectedTable, page)}
              className="p-2 rounded-lg border border-border hover:bg-muted text-muted-foreground">
              <RefreshCw className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {selectedTable && tableInfo && (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {total.toLocaleString()} row{total !== 1 ? 's' : ''} — click any cell to edit
            </span>
            {linkedCols.size > 0 && (
              <span className="text-xs text-indigo-400 flex items-center gap-1">
                <Link2 className="w-3 h-3" />
                {linkedCols.size} join key{linkedCols.size !== 1 ? 's' : ''} defined
              </span>
            )}
          </div>
          <div className="overflow-x-auto">
            {loadingRows ? (
              <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin" />Loading…
              </div>
            ) : rows.length === 0 ? (
              <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">No rows found.</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-muted/50 border-b border-border">
                  <tr>
                    {tableInfo.columns.map((col) => (
                      <th key={col.name} className="px-4 py-3 text-left font-medium text-muted-foreground whitespace-nowrap">
                        {col.name}
                        {col.is_pk && <span className="ml-1 text-xs text-yellow-400">[PK]</span>}
                        {linkedCols.has(col.name) && <span className="ml-1 text-xs text-indigo-400">[join key]</span>}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rows.map((row, i) => (
                    <tr key={i} className="hover:bg-muted/20 transition-colors">
                      {tableInfo.columns.map((col) => (
                        <td key={col.name}
                          className="px-4 py-2 text-foreground whitespace-nowrap max-w-[180px] truncate cursor-pointer hover:bg-primary/10 hover:text-primary transition-colors group"
                          title={`Click to edit ${col.name}`}
                          onClick={() => openEdit(row, col.name)}>
                          {row[col.name] == null
                            ? <span className="text-muted-foreground italic text-xs">null</span>
                            : <span>{String(row[col.name])}</span>}
                          <Edit3 className="w-3 h-3 inline ml-1 opacity-0 group-hover:opacity-50" />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          {total > PAGE_SIZE && (
            <div className="p-4 border-t border-border flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total.toLocaleString()}
              </span>
              <div className="flex items-center gap-2">
                <button onClick={() => setPage((p) => p - 1)} disabled={page === 0} className="p-1.5 rounded border border-border hover:bg-muted disabled:opacity-40"><ChevronLeft className="w-4 h-4" /></button>
                <span className="text-sm px-2">{page + 1} / {totalPages}</span>
                <button onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages - 1} className="p-1.5 rounded border border-border hover:bg-muted disabled:opacity-40"><ChevronRight className="w-4 h-4" /></button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Edit Modal ─────────────────────────────────────────────────── */}
      {editModal && tableInfo && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setEditModal(null)}>
          <div className="bg-card border border-border rounded-2xl w-full max-w-lg shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="p-5 border-b border-border flex items-center justify-between">
              <h3 className="font-semibold text-foreground flex items-center gap-2">
                <Edit3 className="w-4 h-4" /> Edit Cell
              </h3>
              <button onClick={() => setEditModal(null)} className="p-1 rounded hover:bg-muted text-muted-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* What's being edited */}
              <div>
                <p className="text-xs text-muted-foreground mb-1">
                  <span className="font-mono text-foreground">{selectedTable}</span>
                  {' · '}
                  <span className="font-mono text-primary">{editModal.col}</span>
                </p>
                <p className="text-xs text-muted-foreground mb-3">
                  Current value: <span className="font-mono text-foreground bg-muted px-1.5 py-0.5 rounded">{editModal.currentValue || 'null'}</span>
                </p>
                <label className="block text-sm font-medium text-foreground mb-1">New value</label>
                <input
                  type="text" value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSaveEdit()}
                  autoFocus
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-primary text-sm"
                />
              </div>

              {/* ── Cascade section — fully driven by Schema Links ── */}
              <div className="bg-muted/20 rounded-xl border border-border overflow-hidden">
                <div className="flex items-center justify-between p-4">
                  <span className="text-sm font-medium text-foreground flex items-center gap-2">
                    <Link2 className="w-4 h-4 text-indigo-400" /> Cascade to linked tables
                  </span>
                  <button onClick={() => setCascadeOn((v) => !v)}
                    className={`relative w-10 h-5 rounded-full transition-colors ${cascadeOn ? 'bg-primary' : 'bg-muted'}`}>
                    <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${cascadeOn ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </button>
                </div>

                {cascadeOn && (
                  <div className="border-t border-border px-4 pb-4 pt-3 space-y-3">
                    {cascadeGroups.length === 0 ? (
                      /* No relationships defined yet */
                      <div className="flex items-start gap-3 bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
                        <AlertCircle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                        <div>
                          <p className="text-sm text-amber-300 font-medium">No relationships defined for this table</p>
                          <p className="text-xs text-amber-400/80 mt-0.5">
                            Without a defined relationship the system cannot know which column links this table to others.
                          </p>
                          <button onClick={() => { setEditModal(null); onGoToLinks(); }}
                            className="mt-2 text-xs text-amber-300 underline hover:no-underline flex items-center gap-1">
                            <Link2 className="w-3 h-3" /> Define a relationship in Schema Links →
                          </button>
                        </div>
                      </div>
                    ) : (
                      /* Show each relationship group — join column comes from Schema Links */
                      <div className="space-y-2">
                        <p className="text-xs text-muted-foreground">
                          Join keys come from your defined relationships. Each group below will update <span className="font-mono text-primary">{editModal.col}</span> in the linked table(s) by matching on the join key value.
                        </p>
                        {cascadeGroups.map((group) => (
                          <div key={group.joinCol} className="bg-background rounded-lg border border-border p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <span className="text-xs text-muted-foreground">Join key:</span>
                              <span className="font-mono text-xs bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 px-2 py-0.5 rounded">
                                {group.joinCol} = {group.joinValue ?? 'null'}
                              </span>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {group.targets.map((t) => (
                                <span key={t.table}
                                  className="text-xs px-2 py-0.5 rounded-md font-mono border bg-green-500/10 border-green-500/30 text-green-300 flex items-center gap-1">
                                  <CheckCircle2 className="w-3 h-3" />
                                  {t.table}
                                  <span className="opacity-50 text-[10px]">.{t.toCol}</span>
                                  <span className={`text-[10px] ml-0.5 ${t.linkType === 'fk' ? 'text-indigo-400' : 'text-amber-400'}`}>
                                    ({t.linkType})
                                  </span>
                                </span>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <StatusBanner status={updateStatus} />

              <div className="flex items-center gap-3 pt-1">
                <button onClick={handleSaveEdit} disabled={updateStatus.type === 'loading'}
                  className="flex items-center gap-2 bg-primary text-primary-foreground px-5 py-2.5 rounded-lg font-medium hover:opacity-90 disabled:opacity-50 text-sm">
                  {updateStatus.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  {updateStatus.type === 'loading' ? 'Saving…' : cascadeGroups.length > 0 && cascadeOn ? 'Save & Cascade' : 'Save'}
                </button>
                <button onClick={() => setEditModal(null)}
                  className="px-5 py-2.5 rounded-lg border border-border text-muted-foreground hover:text-foreground text-sm">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────── //
// Create Table Panel (manual column definitions)
// ────────────────────────────────────────────────────────────────────────── //

function CreateTablePanel({ onCreated }: { onCreated: () => void }) {
  const [tableName, setTableName] = useState('');
  const [columns, setColumns] = useState<ColumnDef[]>([
    { name: '', type: 'TEXT', nullable: true, is_pk: false },
  ]);
  const [status, setStatus] = useState<StatusState>({ type: 'idle' });

  function updateCol(i: number, field: keyof ColumnDef, value: string | boolean) {
    setColumns((prev) => prev.map((c, idx) => idx === i ? { ...c, [field]: value } : c));
  }

  async function handleCreate() {
    if (!tableName.trim()) { setStatus({ type: 'error', message: 'Table name is required.' }); return; }
    const valid = columns.filter((c) => c.name.trim());
    if (valid.length === 0) { setStatus({ type: 'error', message: 'Add at least one column.' }); return; }
    setStatus({ type: 'loading' });
    try {
      const res = await fetch(`${API_BASE}/admin/table/create-manual`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ table_name: tableName.trim(), columns: valid }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Create failed');
      setStatus({ type: 'success', message: `Table '${data.created}' created with ${data.columns.length} column(s).` });
      setTableName('');
      setColumns([{ name: '', type: 'TEXT', nullable: true, is_pk: false }]);
      onCreated();
    } catch (e) { setStatus({ type: 'error', message: (e as Error).message }); }
  }

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <h2 className="font-semibold text-foreground mb-4 flex items-center gap-2">
        <Table2 className="w-4 h-4" /> Create New Table
      </h2>
      <p className="text-sm text-muted-foreground mb-5">
        Define columns manually. No CSV required — useful when you want to control types and set up schema before importing data.
      </p>

      <div className="mb-4">
        <label className="block text-sm font-medium text-foreground mb-1">Table name</label>
        <input type="text" value={tableName} onChange={(e) => setTableName(e.target.value)}
          placeholder="e.g. customer_metrics"
          className="w-full max-w-sm bg-background border border-border rounded-lg px-4 py-2.5 text-foreground focus:outline-none focus:ring-2 focus:ring-primary text-sm" />
      </div>

      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-foreground">Columns</label>
          <button onClick={() => setColumns((prev) => [...prev, { name: '', type: 'TEXT', nullable: true, is_pk: false }])}
            className="flex items-center gap-1 text-xs text-primary hover:underline">
            <Plus className="w-3 h-3" /> Add column
          </button>
        </div>

        <div className="space-y-2">
          <div className="grid grid-cols-[1fr_130px_80px_60px_32px] gap-2 text-xs text-muted-foreground px-1 mb-1">
            <span>Column name</span><span>Type</span><span>Nullable</span><span>PK</span><span />
          </div>
          {columns.map((col, i) => (
            <div key={i} className="grid grid-cols-[1fr_130px_80px_60px_32px] gap-2 items-center">
              <input type="text" value={col.name} onChange={(e) => updateCol(i, 'name', e.target.value)}
                placeholder="column_name"
                className="bg-background border border-border rounded-lg px-3 py-2 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
              <select value={col.type} onChange={(e) => updateCol(i, 'type', e.target.value)}
                className="bg-background border border-border rounded-lg px-2 py-2 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary">
                {PG_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <div className="flex items-center justify-center">
                <input type="checkbox" checked={col.nullable} onChange={(e) => updateCol(i, 'nullable', e.target.checked)}
                  className="w-4 h-4 accent-primary" />
              </div>
              <div className="flex items-center justify-center">
                <input type="checkbox" checked={col.is_pk} onChange={(e) => updateCol(i, 'is_pk', e.target.checked)}
                  className="w-4 h-4 accent-yellow-400" />
              </div>
              <button onClick={() => columns.length > 1 && setColumns((prev) => prev.filter((_, idx) => idx !== i))}
                disabled={columns.length <= 1}
                className="p-1 rounded hover:bg-destructive/20 text-muted-foreground hover:text-destructive disabled:opacity-30">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      <StatusBanner status={status} className="mb-4" />

      <button onClick={handleCreate} disabled={status.type === 'loading'}
        className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-2.5 rounded-lg font-medium hover:opacity-90 disabled:opacity-50 text-sm">
        {status.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
        {status.type === 'loading' ? 'Creating…' : 'Create Table'}
      </button>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────── //
// Add Columns Panel
// ────────────────────────────────────────────────────────────────────────── //

function AddColumnsPanel({ tables, onAdded }: { tables: TableInfo[]; onAdded: () => void }) {
  const [selectedTable, setSelectedTable] = useState('');
  const [columns, setColumns] = useState<ColumnDef[]>([
    { name: '', type: 'TEXT', nullable: true, is_pk: false },
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  function updateCol(i: number, field: keyof ColumnDef, value: string | boolean) {
    setColumns((prev) => prev.map((c, idx) => idx === i ? { ...c, [field]: value } : c));
  }

  async function handleAddColumns() {
    const validCols = columns.filter((c) => c.name.trim());
    if (!selectedTable || validCols.length === 0) return;
    setLoading(true);
    setError('');
    setSuccess('');
    try {
      const res = await fetch(`${API_BASE}/admin/table/${encodeURIComponent(selectedTable)}/add-columns`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ columns: validCols }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Failed to add columns');
      setSuccess(`Added ${data.columns_added.length} column(s): ${data.columns_added.join(', ')}`);
      setColumns([{ name: '', type: 'TEXT', nullable: true, is_pk: false }]);
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }

  const existingCols = tables.find((t) => t.name === selectedTable)?.columns ?? [];
  const validCols = columns.filter((c) => c.name.trim());
  const canSubmit = !!selectedTable && validCols.length > 0 && !loading;

  return (
    <div className="bg-card border border-border rounded-xl p-6 space-y-5">
      <div>
        <h2 className="font-semibold text-foreground mb-1 flex items-center gap-2">
          <Columns3 className="w-4 h-4" /> Add Columns to Existing Table
        </h2>
        <p className="text-xs text-muted-foreground">
          Select a table and define new columns to add via DDL.
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-foreground mb-1">Table</label>
        <select value={selectedTable} onChange={(e) => setSelectedTable(e.target.value)}
          className="w-full max-w-xs bg-background border border-border rounded-lg px-4 py-2 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary">
          <option value="">— select a table —</option>
          {tables.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
        </select>
      </div>

      {selectedTable && existingCols.length > 0 && (
        <div className="p-3 bg-muted/20 rounded-lg border border-border">
          <p className="text-xs text-muted-foreground mb-2">Existing columns:</p>
          <div className="flex flex-wrap gap-1.5">
            {existingCols.map((c) => (
              <span key={c.name} className={`text-xs px-2 py-0.5 rounded-md font-mono border ${c.is_pk ? 'border-yellow-400/40 text-yellow-400 bg-yellow-400/10' : 'border-border text-muted-foreground'}`}>
                {c.name}
              </span>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-foreground">New columns</label>
          <button onClick={() => setColumns((prev) => [...prev, { name: '', type: 'TEXT', nullable: true, is_pk: false }])}
            className="flex items-center gap-1 text-xs text-primary hover:underline">
            <Plus className="w-3 h-3" /> Add row
          </button>
        </div>
        <div className="space-y-2">
          <div className="grid grid-cols-[1fr_130px_80px_32px] gap-2 text-xs text-muted-foreground px-1 mb-1">
            <span>Column name</span><span>Type</span><span>Nullable</span><span />
          </div>
          {columns.map((col, i) => (
            <div key={i} className="grid grid-cols-[1fr_130px_80px_32px] gap-2 items-center">
              <input type="text" value={col.name} onChange={(e) => updateCol(i, 'name', e.target.value)}
                placeholder="new_column"
                className="bg-background border border-border rounded-lg px-3 py-2 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
              <select value={col.type} onChange={(e) => updateCol(i, 'type', e.target.value)}
                className="bg-background border border-border rounded-lg px-2 py-2 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary">
                {PG_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <div className="flex items-center justify-center">
                <input type="checkbox" checked={col.nullable} onChange={(e) => updateCol(i, 'nullable', e.target.checked)}
                  className="w-4 h-4 accent-primary" />
              </div>
              <button onClick={() => columns.length > 1 && setColumns((prev) => prev.filter((_, idx) => idx !== i))}
                disabled={columns.length <= 1}
                className="p-1 rounded hover:bg-destructive/20 text-muted-foreground hover:text-destructive disabled:opacity-30">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {success && <p className="text-sm text-green-500">{success}</p>}

      <button onClick={handleAddColumns} disabled={!canSubmit}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40">
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
        {loading ? 'Adding columns…' : 'Add Columns'}
      </button>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────── //
// Schema Links Panel (FK / logical link manager)
// ────────────────────────────────────────────────────────────────────────── //

function SchemaLinksPanel({
  tables, relationships, onChanged,
}: {
  tables: TableInfo[];
  relationships: Relationship[];
  onChanged: () => void;
}) {
  const [form, setForm] = useState({
    from_table: '', from_column: '', to_table: '', to_column: '', link_type: 'logical',
  });
  const [status, setStatus] = useState<StatusState>({ type: 'idle' });
  const [deleteStatus, setDeleteStatus] = useState<Record<string, StatusState>>({});
  const [fkCopied, setFkCopied] = useState(false);

  const fromCols = tables.find((t) => t.name === form.from_table)?.columns ?? [];
  const toCols = tables.find((t) => t.name === form.to_table)?.columns ?? [];
  const dbUrl = process.env.NEXT_PUBLIC_DATABASE_URL ?? 'postgresql://USER:PASSWORD@HOST:PORT/DATABASE';

  function buildFkScript(): string {
    const constraint = `fk_${form.from_table}_${form.from_column}_${form.to_table}`;
    return `import psycopg2

conn = psycopg2.connect("${dbUrl}")
cur = conn.cursor()

cur.execute('''
    ALTER TABLE data."${form.from_table}"
    ADD CONSTRAINT "${constraint}"
    FOREIGN KEY ("${form.from_column}")
    REFERENCES data."${form.to_table}" ("${form.to_column}")
''')

conn.commit()
cur.close()
conn.close()
print("Done — FK constraint '${constraint}' created")
`;
  }

  function copyFkScript() {
    navigator.clipboard.writeText(buildFkScript()).then(() => {
      setFkCopied(true);
      setTimeout(() => setFkCopied(false), 2000);
    });
  }

  const fkReady = form.from_table && form.from_column && form.to_table && form.to_column;

  async function handleCreate() {
    if (!form.from_table || !form.from_column || !form.to_table || !form.to_column) {
      setStatus({ type: 'error', message: 'Fill in all fields.' }); return;
    }
    if (form.link_type === 'fk') {
      // FK constraints run DDL — show script instead
      setStatus({ type: 'success', message: 'FK script generated below — copy and run it on a direct DB connection.' });
      return;
    }
    setStatus({ type: 'loading' });
    try {
      const res = await fetch(`${API_BASE}/admin/schema/relationships`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Failed');
      setStatus({ type: 'success', message: `Link '${data.created}' (${data.link_type}) created.` });
      setForm({ from_table: '', from_column: '', to_table: '', to_column: '', link_type: 'logical' });
      onChanged();
    } catch (e) { setStatus({ type: 'error', message: (e as Error).message }); }
  }

  async function handleDelete(rel: Relationship) {
    setDeleteStatus((prev) => ({ ...prev, [rel.constraint_name]: { type: 'loading' } }));
    try {
      const res = await fetch(
        `${API_BASE}/admin/schema/relationships/${encodeURIComponent(rel.constraint_name)}?from_table=${encodeURIComponent(rel.from_table)}`,
        { method: 'DELETE', headers: authHeaders() }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Delete failed');
      setDeleteStatus((prev) => ({ ...prev, [rel.constraint_name]: { type: 'success', message: 'Removed' } }));
      onChanged();
    } catch (e) {
      setDeleteStatus((prev) => ({ ...prev, [rel.constraint_name]: { type: 'error', message: (e as Error).message } }));
    }
  }

  return (
    <div className="space-y-5">
      {/* Existing relationships */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="p-5 border-b border-border">
          <h2 className="font-semibold text-foreground flex items-center gap-2">
            <Link2 className="w-4 h-4" /> Table Links
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Links define how tables share a common key column. When you edit a value in a linked column,
            the change can cascade to all tables sharing that key — even if rows are in different order.
          </p>
        </div>

        {relationships.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-sm">
            No links defined yet. Create one below.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b border-border">
              <tr>
                <th className="px-5 py-3 text-left font-medium text-muted-foreground">From</th>
                <th className="px-5 py-3 text-left font-medium text-muted-foreground">→ To</th>
                <th className="px-5 py-3 text-left font-medium text-muted-foreground">Type</th>
                <th className="px-5 py-3 text-left font-medium text-muted-foreground">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {relationships.map((rel) => {
                const ds = deleteStatus[rel.constraint_name] ?? { type: 'idle' };
                return (
                  <tr key={rel.constraint_name} className="hover:bg-muted/20">
                    <td className="px-5 py-3 font-mono text-xs">
                      <span className="text-foreground">{rel.from_table}</span>
                      <span className="text-muted-foreground">.</span>
                      <span className="text-indigo-400">{rel.from_column}</span>
                    </td>
                    <td className="px-5 py-3 font-mono text-xs">
                      <span className="text-foreground">{rel.to_table}</span>
                      <span className="text-muted-foreground">.</span>
                      <span className="text-indigo-400">{rel.to_column}</span>
                    </td>
                    <td className="px-5 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${rel.link_type === 'fk' ? 'bg-indigo-500/20 text-indigo-300' : 'bg-amber-500/20 text-amber-300'}`}>
                        {rel.link_type === 'fk' ? 'FK constraint' : 'Logical link'}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      {ds.type === 'error'
                        ? <span className="text-xs text-destructive">{(ds as { type: 'error'; message: string }).message}</span>
                        : ds.type === 'success'
                          ? <CheckCircle2 className="w-4 h-4 text-green-400" />
                          : (
                            <button onClick={() => handleDelete(rel)} disabled={ds.type === 'loading'}
                              className="flex items-center gap-1 text-xs text-destructive/70 hover:text-destructive disabled:opacity-50">
                              {ds.type === 'loading' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Link2Off className="w-3 h-3" />}
                              Remove
                            </button>
                          )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Add new link */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h3 className="font-semibold text-foreground mb-1">Define New Link</h3>
        <p className="text-sm text-muted-foreground mb-4">
          Choose two tables that share a common column (e.g. table <em>A,B,C</em> and <em>A,C,D</em> both have column <em>C</em>).
          Set <em>C</em> as the join key — changes to linked columns will cascade to matching rows regardless of row order.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">From table</label>
            <select value={form.from_table} onChange={(e) => setForm((f) => ({ ...f, from_table: e.target.value, from_column: '' }))}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary">
              <option value="">— table —</option>
              {tables.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">From column (join key)</label>
            <select value={form.from_column} onChange={(e) => setForm((f) => ({ ...f, from_column: e.target.value }))}
              disabled={!form.from_table}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50">
              <option value="">— column —</option>
              {fromCols.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.type})</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">To table</label>
            <select value={form.to_table} onChange={(e) => setForm((f) => ({ ...f, to_table: e.target.value, to_column: '' }))}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary">
              <option value="">— table —</option>
              {tables.filter((t) => t.name !== form.from_table).map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">To column (same key)</label>
            <select value={form.to_column} onChange={(e) => setForm((f) => ({ ...f, to_column: e.target.value }))}
              disabled={!form.to_table}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50">
              <option value="">— column —</option>
              {toCols.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.type})</option>)}
            </select>
          </div>
        </div>

        <div className="mb-4">
          <label className="text-xs text-muted-foreground mb-1 block">Link type</label>
          <div className="flex gap-3">
            {(['logical', 'fk'] as const).map((lt) => (
              <label key={lt} className="flex items-center gap-2 cursor-pointer">
                <input type="radio" value={lt} checked={form.link_type === lt}
                  onChange={() => setForm((f) => ({ ...f, link_type: lt }))}
                  className="accent-primary" />
                <span className="text-sm text-foreground">
                  {lt === 'logical' ? 'Logical link (recommended — no constraint, always works)' : 'FK constraint (strict — requires matching values)'}
                </span>
              </label>
            ))}
          </div>
        </div>

        <StatusBanner status={status} className="mb-4" />

        <div className="flex items-center gap-3">
          <button onClick={handleCreate} disabled={status.type === 'loading'}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-2.5 rounded-lg font-medium hover:opacity-90 disabled:opacity-50 text-sm">
            {status.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />}
            {status.type === 'loading' ? 'Creating…' : form.link_type === 'fk' ? 'Generate FK Script' : 'Create Link'}
          </button>
          {form.link_type === 'fk' && (
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Terminal className="w-3 h-3" /> FK constraints require DDL — a script will be generated
            </p>
          )}
        </div>

        {/* FK Script output */}
        {form.link_type === 'fk' && fkReady && status.type === 'success' && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-foreground">Generated FK script</p>
              <button onClick={copyFkScript}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:opacity-90">
                <Copy className="w-3 h-3" />
                {fkCopied ? 'Copied!' : 'Copy script'}
              </button>
            </div>
            <pre className="bg-background border border-border rounded-lg p-4 text-xs font-mono text-foreground overflow-x-auto whitespace-pre leading-relaxed">
              {buildFkScript()}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────── //
// Users Management Tab (unchanged)
// ────────────────────────────────────────────────────────────────────────── //

function UsersTab() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [profileInputs, setProfileInputs] = useState<Record<string, string>>({});
  const [saveStatus, setSaveStatus] = useState<Record<string, StatusState>>({});

  const loadUsers = useCallback(() => {
    setLoading(true);
    fetch(`${API_BASE}/admin/users`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => {
        const list: User[] = d.users ?? [];
        setUsers(list);
        const init: Record<string, string> = {};
        list.forEach((u) => { init[u.user_id] = u.user_profile; });
        setProfileInputs(init);
      })
      .catch(() => setUsers([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  async function handleSaveProfile(userId: string) {
    const profile = profileInputs[userId]?.trim();
    if (!profile) return;
    setSaveStatus((prev) => ({ ...prev, [userId]: { type: 'loading' } }));
    try {
      const res = await fetch(`${API_BASE}/admin/users/${userId}/profile`, {
        method: 'PATCH',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_profile: profile }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Failed');
      setSaveStatus((prev) => ({ ...prev, [userId]: { type: 'success', message: 'Saved' } }));
      setUsers((prev) => prev.map((u) => u.user_id === userId ? { ...u, user_profile: data.user_profile } : u));
    } catch (e) {
      setSaveStatus((prev) => ({ ...prev, [userId]: { type: 'error', message: (e as Error).message } }));
    }
  }

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="p-6 border-b border-border flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
          <Users className="w-5 h-5" /> Registered Users
        </h2>
        <button onClick={loadUsers} className="p-2 rounded-lg border border-border hover:bg-muted text-muted-foreground"><RefreshCw className="w-4 h-4" /></button>
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground"><Loader2 className="w-5 h-5 animate-spin" />Loading users…</div>
      ) : users.length === 0 ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground text-sm">No users found.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b border-border">
              <tr>
                <th className="px-6 py-3 text-left font-medium text-muted-foreground">Email</th>
                <th className="px-6 py-3 text-left font-medium text-muted-foreground">Role</th>
                <th className="px-6 py-3 text-left font-medium text-muted-foreground">User Profile</th>
                <th className="px-6 py-3 text-left font-medium text-muted-foreground">Joined</th>
                <th className="px-6 py-3 text-left font-medium text-muted-foreground">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((user) => {
                const status = saveStatus[user.user_id] ?? { type: 'idle' };
                return (
                  <tr key={user.user_id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-6 py-3 text-foreground">{user.email}</td>
                    <td className="px-6 py-3">
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${user.role === 'admin' ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'}`}>{user.role}</span>
                    </td>
                    <td className="px-6 py-3">
                      <input type="text" value={profileInputs[user.user_id] ?? user.user_profile}
                        onChange={(e) => setProfileInputs((prev) => ({ ...prev, [user.user_id]: e.target.value }))}
                        className="w-36 bg-background border border-border rounded-lg px-3 py-1.5 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
                    </td>
                    <td className="px-6 py-3 text-muted-foreground text-xs">
                      {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-2">
                        <button onClick={() => handleSaveProfile(user.user_id)} disabled={status.type === 'loading'}
                          className="flex items-center gap-1.5 bg-primary text-primary-foreground px-3 py-1.5 rounded-lg text-xs font-medium hover:opacity-90 disabled:opacity-50">
                          {status.type === 'loading' ? <Loader2 className="w-3 h-3 animate-spin" /> : <UserCheck className="w-3 h-3" />}
                          Save
                        </button>
                        {status.type === 'success' && <CheckCircle2 className="w-4 h-4 text-green-400" />}
                        {status.type === 'error' && <span className="text-xs text-destructive">{(status as { type: 'error'; message: string }).message}</span>}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="p-4 border-t border-border">
        <p className="text-xs text-muted-foreground">
          To assign the <span className="font-medium">admin</span> role, set{' '}
          <code className="bg-muted px-1 py-0.5 rounded">role = 'admin'</code> directly in PostgreSQL.
        </p>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────── //
// Shared UI components
// ────────────────────────────────────────────────────────────────────────── //

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}>
      {children}
    </button>
  );
}

function StepBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="bg-primary/20 text-primary rounded-full w-6 h-6 flex items-center justify-center shrink-0">
      {children}
    </span>
  );
}

function DropZone({ file, dragOver, inputRef, onDragOver, onDragLeave, onDrop, onChange }: {
  file: File | null; dragOver: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onDragOver: () => void; onDragLeave: () => void;
  onDrop: (f: File) => void; onChange: (f: File) => void;
}) {
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); onDragOver(); }}
      onDragLeave={onDragLeave}
      onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) onDrop(f); }}
      onClick={() => inputRef.current?.click()}
      className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${dragOver ? 'border-primary bg-primary/10' : 'border-border hover:border-muted-foreground/60'}`}>
      <Upload className="w-7 h-7 mx-auto mb-2 text-muted-foreground" />
      {file ? (
        <p className="font-medium text-foreground text-sm">{file.name}</p>
      ) : (
        <p className="text-muted-foreground text-sm">
          Drag & drop a <span className="font-semibold">.csv</span> file, or <span className="text-primary underline">click to browse</span>
        </p>
      )}
      <input ref={inputRef} type="file" accept=".csv" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onChange(f); }} />
    </div>
  );
}

function StatusBanner({ status, className = '' }: { status: StatusState; className?: string }) {
  if (status.type === 'idle' || status.type === 'loading') return null;
  const isError = status.type === 'error';
  return (
    <div className={`flex items-start gap-2 text-sm rounded-lg p-3 border ${isError ? 'text-destructive bg-destructive/10 border-destructive/20' : 'text-green-400 bg-green-400/10 border-green-400/20'} ${className}`}>
      {isError ? <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" /> : <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />}
      <span>{status.message}</span>
    </div>
  );
}
