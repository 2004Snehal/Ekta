'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Upload,
  Trash2,
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  RefreshCw,
  Users,
  Database,
  Plus,
  UserCheck,
} from 'lucide-react';

// ------------------------------------------------------------------ //
// Types
// ------------------------------------------------------------------ //

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

type Tab = 'data' | 'users';

// ------------------------------------------------------------------ //
// Constants
// ------------------------------------------------------------------ //

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '');
const PAGE_SIZE = 50;

function authHeaders(): HeadersInit {
  const token = typeof window !== 'undefined'
    ? localStorage.getItem('frammer_token')
    : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ------------------------------------------------------------------ //
// Page
// ------------------------------------------------------------------ //

export default function AdminPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>('data');
  const [authChecked, setAuthChecked] = useState(false);

  // Guard: redirect non-admins
  useEffect(() => {
    const raw = localStorage.getItem('frammer_user');
    if (!raw) { router.replace('/login'); return; }
    try {
      const user = JSON.parse(raw);
      if (user.role !== 'admin') { router.replace('/dashboard'); return; }
    } catch {
      router.replace('/login'); return;
    }
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
      <div className="max-w-6xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground">Admin Console</h1>
          <p className="text-muted-foreground mt-1">
            Manage data schema tables and user profiles.
          </p>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-muted/30 p-1 rounded-xl w-fit">
          <TabButton active={activeTab === 'data'} onClick={() => setActiveTab('data')}>
            <Database className="w-4 h-4" />
            Data Management
          </TabButton>
          <TabButton active={activeTab === 'users'} onClick={() => setActiveTab('users')}>
            <Users className="w-4 h-4" />
            User Management
          </TabButton>
        </div>

        {activeTab === 'data' ? <DataTab /> : <UsersTab />}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ //
// Data Management Tab
// ------------------------------------------------------------------ //

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

  // CSV for new table creation
  const [newTableName, setNewTableName] = useState('');
  const [newTableFile, setNewTableFile] = useState<File | null>(null);
  const [newTableStatus, setNewTableStatus] = useState<StatusState>({ type: 'idle' });
  const [newTableDrag, setNewTableDrag] = useState(false);
  const newTableInputRef = useRef<HTMLInputElement>(null);

  // CSV for append
  const [appendFile, setAppendFile] = useState<File | null>(null);
  const [appendDrag, setAppendDrag] = useState(false);
  const [appendStatus, setAppendStatus] = useState<StatusState>({ type: 'idle' });
  const appendInputRef = useRef<HTMLInputElement>(null);

  const [deleteStatus, setDeleteStatus] = useState<StatusState>({ type: 'idle' });
  const [dropStatus, setDropStatus] = useState<StatusState>({ type: 'idle' });

  // Load table list
  const loadTables = useCallback(() => {
    setLoadingTables(true);
    fetch(`${API_BASE}/admin/tables`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => setTables(d.tables ?? []))
      .catch(() => setTables([]))
      .finally(() => setLoadingTables(false));
  }, []);

  useEffect(() => { loadTables(); }, [loadTables]);

  // Load rows
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
    setSelectedTable(name);
    setPage(0);
    setRows([]);
    setTotal(0);
    setAppendFile(null);
    setAppendStatus({ type: 'idle' });
    setDeleteStatus({ type: 'idle' });
    setDropStatus({ type: 'idle' });
  }

  const pkCol = tableInfo?.primary_keys[0] ?? null;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  function toggleRow(pk: string | number) {
    setSelectedPks((prev) => {
      const next = new Set(prev);
      next.has(pk) ? next.delete(pk) : next.add(pk);
      return next;
    });
  }

  function toggleAll() {
    if (!pkCol) return;
    const all = rows.map((r) => r[pkCol] as string | number);
    setSelectedPks(selectedPks.size === rows.length ? new Set() : new Set(all));
  }

  // Create new table
  async function handleCreateTable() {
    if (!newTableFile || !newTableName.trim()) return;
    setNewTableStatus({ type: 'loading' });
    const form = new FormData();
    form.append('file', newTableFile);
    try {
      const res = await fetch(
        `${API_BASE}/admin/table/${newTableName.trim()}/upload-csv`,
        { method: 'POST', headers: authHeaders(), body: form }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Failed');
      setNewTableStatus({
        type: 'success',
        message: `Table '${data.table}' ${data.action} with ${data.inserted} rows.`,
      });
      setNewTableFile(null);
      setNewTableName('');
      if (newTableInputRef.current) newTableInputRef.current.value = '';
      loadTables();
    } catch (e) {
      setNewTableStatus({ type: 'error', message: (e as Error).message });
    }
  }

  // Append rows
  async function handleAppend() {
    if (!appendFile || !selectedTable) return;
    setAppendStatus({ type: 'loading' });
    const form = new FormData();
    form.append('file', appendFile);
    try {
      const res = await fetch(
        `${API_BASE}/admin/table/${selectedTable}/append-csv`,
        { method: 'POST', headers: authHeaders(), body: form }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Failed');
      setAppendStatus({ type: 'success', message: `Inserted ${data.inserted} rows into ${data.table}.` });
      setAppendFile(null);
      if (appendInputRef.current) appendInputRef.current.value = '';
      loadRows(selectedTable, page);
    } catch (e) {
      setAppendStatus({ type: 'error', message: (e as Error).message });
    }
  }

  // Delete selected rows
  async function handleDeleteRows() {
    if (!pkCol || selectedPks.size === 0) return;
    setDeleteStatus({ type: 'loading' });
    try {
      const res = await fetch(
        `${API_BASE}/admin/table/${selectedTable}/rows`,
        {
          method: 'DELETE',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ primary_key_column: pkCol, values: Array.from(selectedPks) }),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Delete failed');
      setDeleteStatus({ type: 'success', message: `Deleted ${data.deleted} row(s).` });
      setSelectedPks(new Set());
      loadRows(selectedTable, page);
    } catch (e) {
      setDeleteStatus({ type: 'error', message: (e as Error).message });
    }
  }

  // Drop table
  async function handleDropTable() {
    if (!selectedTable) return;
    if (!window.confirm(`Permanently drop table '${selectedTable}'? This cannot be undone.`)) return;
    setDropStatus({ type: 'loading' });
    try {
      const res = await fetch(
        `${API_BASE}/admin/table/${selectedTable}`,
        { method: 'DELETE', headers: authHeaders() }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Drop failed');
      setDropStatus({ type: 'success', message: `Table '${data.dropped}' dropped.` });
      setSelectedTable('');
      setRows([]);
      loadTables();
    } catch (e) {
      setDropStatus({ type: 'error', message: (e as Error).message });
    }
  }

  return (
    <div className="space-y-6">

      {/* ── Create new table ─────────────────────────────────── */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
          <StepBadge><Plus className="w-3 h-3" /></StepBadge>
          Create New Table from CSV
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          Drag and drop a CSV file to create a brand-new table in the data schema.
          Column types are inferred as TEXT; an auto-increment <code className="text-xs bg-muted px-1 py-0.5 rounded">_row_id</code> primary key is added.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 mb-3">
          <input
            type="text"
            value={newTableName}
            onChange={(e) => setNewTableName(e.target.value)}
            placeholder="table_name (letters, numbers, underscores)"
            className="flex-1 bg-background border border-border rounded-lg px-4 py-2.5 text-foreground focus:outline-none focus:ring-2 focus:ring-primary text-sm"
          />
        </div>

        <DropZone
          file={newTableFile}
          dragOver={newTableDrag}
          inputRef={newTableInputRef}
          onDragOver={() => setNewTableDrag(true)}
          onDragLeave={() => setNewTableDrag(false)}
          onDrop={(f) => { setNewTableFile(f); setNewTableDrag(false); setNewTableStatus({ type: 'idle' }); }}
          onChange={(f) => { setNewTableFile(f); setNewTableStatus({ type: 'idle' }); }}
        />

        <StatusBanner status={newTableStatus} className="mt-3" />

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleCreateTable}
            disabled={!newTableFile || !newTableName.trim() || newTableStatus.type === 'loading'}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-2.5 rounded-lg font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
          >
            {newTableStatus.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            {newTableStatus.type === 'loading' ? 'Creating…' : 'Create Table'}
          </button>
          {newTableFile && newTableStatus.type !== 'loading' && (
            <button
              onClick={() => { setNewTableFile(null); setNewTableStatus({ type: 'idle' }); if (newTableInputRef.current) newTableInputRef.current.value = ''; }}
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* ── Select existing table ─────────────────────────────── */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
          <StepBadge><Database className="w-3 h-3" /></StepBadge>
          Manage Existing Table
        </h2>

        {loadingTables ? (
          <span className="flex items-center gap-2 text-muted-foreground text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading tables…
          </span>
        ) : (
          <div className="flex items-center gap-3">
            <select
              value={selectedTable}
              onChange={(e) => handleTableChange(e.target.value)}
              className="w-full max-w-sm bg-background border border-border rounded-lg px-4 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-primary text-sm"
            >
              <option value="">— choose a table —</option>
              {tables.map((t) => (
                <option key={t.name} value={t.name}>{t.name}</option>
              ))}
            </select>
            {selectedTable && (
              <button
                onClick={handleDropTable}
                disabled={dropStatus.type === 'loading'}
                className="flex items-center gap-2 bg-destructive/10 text-destructive border border-destructive/30 px-4 py-2 rounded-lg text-sm font-medium hover:bg-destructive/20 disabled:opacity-50"
              >
                {dropStatus.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                Drop Table
              </button>
            )}
          </div>
        )}
        <StatusBanner status={dropStatus} className="mt-3" />
      </div>

      {/* ── Table rows ────────────────────────────────────────── */}
      {selectedTable && tableInfo && (
        <>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="p-6 border-b border-border flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-foreground">
                Table Data
                <span className="text-sm font-normal text-muted-foreground ml-2">
                  — {total.toLocaleString()} row{total !== 1 ? 's' : ''}
                </span>
              </h2>
              <div className="flex items-center gap-2">
                <button onClick={() => loadRows(selectedTable, page)} className="p-2 rounded-lg border border-border hover:bg-muted text-muted-foreground" title="Refresh">
                  <RefreshCw className="w-4 h-4" />
                </button>
                {selectedPks.size > 0 && (
                  <button
                    onClick={handleDeleteRows}
                    disabled={deleteStatus.type === 'loading'}
                    className="flex items-center gap-2 bg-destructive text-destructive-foreground px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
                  >
                    {deleteStatus.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                    Delete {selectedPks.size} selected
                  </button>
                )}
              </div>
            </div>
            <StatusBanner status={deleteStatus} className="mx-6 mt-4" />

            <div className="overflow-x-auto">
              {loadingRows ? (
                <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin" /> Loading rows…
                </div>
              ) : rows.length === 0 ? (
                <div className="flex items-center justify-center py-16 text-muted-foreground text-sm">No rows found.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 border-b border-border">
                    <tr>
                      {pkCol && (
                        <th className="px-4 py-3 w-10">
                          <input type="checkbox" checked={selectedPks.size === rows.length && rows.length > 0} onChange={toggleAll} className="rounded accent-primary" />
                        </th>
                      )}
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
                          {pkCol && (
                            <td className="px-4 py-2">
                              <input type="checkbox" checked={selected} onChange={() => pkVal !== null && pkVal !== undefined && toggleRow(pkVal)} className="rounded accent-primary" />
                            </td>
                          )}
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
                <span className="text-sm text-muted-foreground">
                  {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total.toLocaleString()}
                </span>
                <div className="flex items-center gap-2">
                  <button onClick={() => setPage((p) => p - 1)} disabled={page === 0} className="p-1.5 rounded border border-border hover:bg-muted disabled:opacity-40">
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <span className="text-sm px-2 text-foreground">{page + 1} / {totalPages}</span>
                  <button onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages - 1} className="p-1.5 rounded border border-border hover:bg-muted disabled:opacity-40">
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Append rows */}
          <div className="bg-card border border-border rounded-xl p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
              <StepBadge><Upload className="w-3 h-3" /></StepBadge>
              Append Rows to <code className="text-primary text-sm">{selectedTable}</code>
            </h2>

            {/* Column legend */}
            <div className="mb-4">
              <p className="text-sm text-muted-foreground mb-2">
                CSV columns must match the table schema (case-insensitive). Auto-generated columns may be omitted.
              </p>
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

            <DropZone
              file={appendFile}
              dragOver={appendDrag}
              inputRef={appendInputRef}
              onDragOver={() => setAppendDrag(true)}
              onDragLeave={() => setAppendDrag(false)}
              onDrop={(f) => { setAppendFile(f); setAppendDrag(false); setAppendStatus({ type: 'idle' }); }}
              onChange={(f) => { setAppendFile(f); setAppendStatus({ type: 'idle' }); }}
            />
            <StatusBanner status={appendStatus} className="mt-3" />

            <div className="mt-4 flex items-center gap-3">
              <button
                onClick={handleAppend}
                disabled={!appendFile || appendStatus.type === 'loading'}
                className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-2.5 rounded-lg font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                {appendStatus.type === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                {appendStatus.type === 'loading' ? 'Uploading…' : 'Upload & Append'}
              </button>
              {appendFile && appendStatus.type !== 'loading' && (
                <button onClick={() => { setAppendFile(null); setAppendStatus({ type: 'idle' }); if (appendInputRef.current) appendInputRef.current.value = ''; }} className="text-sm text-muted-foreground hover:text-foreground">Clear</button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ //
// Users Management Tab
// ------------------------------------------------------------------ //

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
          <Users className="w-5 h-5" />
          Registered Users
        </h2>
        <button onClick={loadUsers} className="p-2 rounded-lg border border-border hover:bg-muted text-muted-foreground" title="Refresh">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading users…
        </div>
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
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${user.role === 'admin' ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'}`}>
                        {user.role}
                      </span>
                    </td>
                    <td className="px-6 py-3">
                      <input
                        type="text"
                        value={profileInputs[user.user_id] ?? user.user_profile}
                        onChange={(e) => setProfileInputs((prev) => ({ ...prev, [user.user_id]: e.target.value }))}
                        className="w-36 bg-background border border-border rounded-lg px-3 py-1.5 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                    </td>
                    <td className="px-6 py-3 text-muted-foreground text-xs">
                      {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleSaveProfile(user.user_id)}
                          disabled={status.type === 'loading'}
                          className="flex items-center gap-1.5 bg-primary text-primary-foreground px-3 py-1.5 rounded-lg text-xs font-medium hover:opacity-90 disabled:opacity-50"
                        >
                          {status.type === 'loading' ? <Loader2 className="w-3 h-3 animate-spin" /> : <UserCheck className="w-3 h-3" />}
                          Save
                        </button>
                        {status.type === 'success' && (
                          <CheckCircle2 className="w-4 h-4 text-green-400" />
                        )}
                        {status.type === 'error' && (
                          <span className="text-xs text-destructive">{(status as { type: 'error'; message: string }).message}</span>
                        )}
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
          To assign the <span className="font-medium">admin</span> role to a user, set{' '}
          <code className="bg-muted px-1 py-0.5 rounded">role = 'admin'</code> directly in the PostgreSQL database.
        </p>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ //
// Shared sub-components
// ------------------------------------------------------------------ //

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
        active
          ? 'bg-primary text-primary-foreground'
          : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
      }`}
    >
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

function DropZone({
  file,
  dragOver,
  inputRef,
  onDragOver,
  onDragLeave,
  onDrop,
  onChange,
}: {
  file: File | null;
  dragOver: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onDragOver: () => void;
  onDragLeave: () => void;
  onDrop: (f: File) => void;
  onChange: (f: File) => void;
}) {
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); onDragOver(); }}
      onDragLeave={onDragLeave}
      onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) onDrop(f); }}
      onClick={() => inputRef.current?.click()}
      className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
        dragOver ? 'border-primary bg-primary/10' : 'border-border hover:border-muted-foreground/60'
      }`}
    >
      <Upload className="w-7 h-7 mx-auto mb-2 text-muted-foreground" />
      {file ? (
        <p className="font-medium text-foreground text-sm">{file.name}</p>
      ) : (
        <p className="text-muted-foreground text-sm">
          Drag & drop a <span className="font-semibold">.csv</span> file, or{' '}
          <span className="text-primary underline">click to browse</span>
        </p>
      )}
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onChange(f); }}
      />
    </div>
  );
}

function StatusBanner({
  status,
  className = '',
}: {
  status: StatusState;
  className?: string;
}) {
  if (status.type === 'idle' || status.type === 'loading') return null;
  const isError = status.type === 'error';
  return (
    <div className={`flex items-start gap-2 text-sm rounded-lg p-3 border ${isError ? 'text-destructive bg-destructive/10 border-destructive/20' : 'text-green-400 bg-green-400/10 border-green-400/20'} ${className}`}>
      {isError ? <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" /> : <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />}
      <span>{status.message}</span>
    </div>
  );
}
