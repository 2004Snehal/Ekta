'use client';

import { useEffect, useState } from 'react';
import { X, Save, Trash2, Download } from 'lucide-react';

interface TeamMember {
  id: string;
  name: string;
  profile: string;
  role: string;
}

interface SavedDashboard {
  id: string;
  name: string;
  description?: string;
  created_by: string;
  created_by_name?: string;
  visible_kpi_ids: string[];
  graphs: { source: string; index: number }[];
  created_at: string;
}

interface WorkspacePanelProps {
  isOpen: boolean;
  onClose: () => void;
  apiBaseUrl: string;
  currentUserId: string;
  currentUserName?: string;
  visibleKpiIds: string[];
  visibleGraphIndices: number[];
  onLoadDashboard: (visibleKpiIds: string[], visibleGraphIndices: number[]) => void;
}

const PROFILE_LABELS: Record<string, string> = {
  founder:        'Founder',
  client_success: 'Client Success',
  operations:     'Operations',
  editorial:      'Editorial',
  tech_product:   'Tech & Product',
  team_member:    'Team Member',
  admin:          'Admin',
  user:           'User',
};

const PROFILE_COLOUR: Record<string, string> = {
  founder:        'var(--signal)',
  client_success: 'var(--uplink)',
  operations:     'var(--warn)',
  editorial:      'var(--ok)',
  tech_product:   '#9b59b6',
  team_member:    'var(--on-mid)',
};

export function WorkspacePanel({
  isOpen, onClose, apiBaseUrl, currentUserId, currentUserName,
  visibleKpiIds, visibleGraphIndices, onLoadDashboard,
}: WorkspacePanelProps) {
  const [tab, setTab]           = useState<'team' | 'dashboards'>('team');
  const [grouped, setGrouped]   = useState<Record<string, TeamMember[]>>({});
  const [dashboards, setDashboards] = useState<SavedDashboard[]>([]);
  const [saveName, setSaveName] = useState('');
  const [saveDesc, setSaveDesc] = useState('');
  const [saving, setSaving]     = useState(false);
  const [saveMsg, setSaveMsg]   = useState('');

  useEffect(() => {
    if (!isOpen || !apiBaseUrl) return;
    fetch(`${apiBaseUrl}/workspace/team`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.grouped) setGrouped(d.grouped); })
      .catch(() => {});
    loadDashboards();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, apiBaseUrl]);

  function loadDashboards() {
    if (!apiBaseUrl) return;
    fetch(`${apiBaseUrl}/workspace/dashboards`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.dashboards) setDashboards(d.dashboards); })
      .catch(() => {});
  }

  async function handleSave() {
    if (!saveName.trim() || !apiBaseUrl || saving) return;
    setSaving(true); setSaveMsg('');
    try {
      const graphs = visibleGraphIndices.map(idx => ({ source: 'builtin', index: idx }));
      const res = await fetch(`${apiBaseUrl}/workspace/dashboards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: saveName.trim(),
          description: saveDesc.trim() || null,
          created_by: currentUserId,
          created_by_name: currentUserName ?? null,
          visible_kpi_ids: visibleKpiIds,
          graphs,
        }),
      });
      if (!res.ok) throw new Error();
      setSaveMsg('Saved ✓'); setSaveName(''); setSaveDesc('');
      loadDashboards();
      setTimeout(() => setSaveMsg(''), 3000);
    } catch { setSaveMsg('Save failed.'); }
    finally { setSaving(false); }
  }

  async function handleDelete(id: string) {
    await fetch(`${apiBaseUrl}/workspace/dashboards/${id}?user_id=${encodeURIComponent(currentUserId)}`, { method: 'DELETE' }).catch(() => {});
    loadDashboards();
  }

  function handleLoad(d: SavedDashboard) {
    const indices = d.graphs.filter(g => g.source === 'builtin' && typeof g.index === 'number').map(g => g.index);
    onLoadDashboard(d.visible_kpi_ids.length > 0 ? d.visible_kpi_ids : [], indices.length > 0 ? indices : [0, 1, 2, 3]);
    onClose();
  }

  if (!isOpen) return null;

  const mono: React.CSSProperties = { fontFamily: 'var(--font-mono)' };

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 900 }} />
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: '420px',
        background: 'var(--surface)', borderLeft: '1px solid var(--wire)',
        zIndex: 901, display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: '1px solid var(--wire)' }}>
          <span style={{ ...mono, fontSize: '0.65rem', letterSpacing: '0.18em', color: 'var(--on-mid)', textTransform: 'uppercase' }}>Workspace</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--on-mid)', padding: 4, display: 'flex' }}><X size={15} /></button>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--wire)' }}>
          {(['team', 'dashboards'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              flex: 1, padding: '10px 0', background: 'none', border: 'none', cursor: 'pointer',
              ...mono, fontSize: '0.6rem', letterSpacing: '0.12em', textTransform: 'uppercase',
              color: tab === t ? 'var(--on)' : 'var(--on-low)',
              borderBottom: tab === t ? '2px solid var(--signal)' : '2px solid transparent',
            }}>{t === 'team' ? 'Team' : 'Dashboards'}</button>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>

          {/* TEAM */}
          {tab === 'team' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {Object.keys(grouped).length === 0 && <p style={{ fontSize: '0.75rem', color: 'var(--on-low)' }}>No team members found.</p>}
              {Object.entries(grouped).map(([profile, members]) => (
                <div key={profile}>
                  <div style={{ ...mono, fontSize: '0.55rem', letterSpacing: '0.16em', textTransform: 'uppercase', color: PROFILE_COLOUR[profile] ?? 'var(--on-mid)', marginBottom: '8px' }}>
                    {PROFILE_LABELS[profile] ?? profile} <span style={{ color: 'var(--on-low)' }}>({members.length})</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                    {members.map(m => (
                      <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px', background: 'var(--surface-hi)', borderRadius: '2px' }}>
                        <div style={{
                          width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
                          background: `color-mix(in srgb, ${PROFILE_COLOUR[profile] ?? 'var(--on-mid)'} 15%, transparent)`,
                          border: `1px solid ${PROFILE_COLOUR[profile] ?? 'var(--wire-hi)'}`,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          ...mono, fontSize: '0.65rem', color: PROFILE_COLOUR[profile] ?? 'var(--on-mid)',
                        }}>
                          {(m.name || '?')[0].toUpperCase()}
                        </div>
                        <div>
                          <div style={{ fontSize: '0.8rem', color: 'var(--on)', fontWeight: 500 }}>{m.name}</div>
                          <div style={{ ...mono, fontSize: '0.55rem', color: 'var(--on-low)', marginTop: '1px' }}>{PROFILE_LABELS[m.profile] ?? m.profile}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* DASHBOARDS */}
          {tab === 'dashboards' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Save form */}
              <div style={{ background: 'var(--surface-hi)', padding: '14px', borderRadius: '2px' }}>
                <div style={{ ...mono, fontSize: '0.55rem', letterSpacing: '0.13em', textTransform: 'uppercase', color: 'var(--on-mid)', marginBottom: '10px' }}>Save Current Dashboard</div>
                <input value={saveName} onChange={e => setSaveName(e.target.value)} onKeyDown={e => e.key === 'Enter' && void handleSave()} placeholder="Dashboard name…"
                  style={{ width: '100%', boxSizing: 'border-box', background: 'var(--surface)', border: '1px solid var(--wire)', color: 'var(--on)', padding: '6px 8px', fontSize: '0.78rem', borderRadius: '2px', outline: 'none', marginBottom: '6px' }} />
                <input value={saveDesc} onChange={e => setSaveDesc(e.target.value)} placeholder="Description (optional)…"
                  style={{ width: '100%', boxSizing: 'border-box', background: 'var(--surface)', border: '1px solid var(--wire)', color: 'var(--on)', padding: '6px 8px', fontSize: '0.78rem', borderRadius: '2px', outline: 'none', marginBottom: '10px' }} />
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <button onClick={() => void handleSave()} disabled={saving || !saveName.trim()} style={{
                    display: 'flex', alignItems: 'center', gap: '5px', padding: '5px 14px',
                    background: saveName.trim() ? 'var(--signal)' : 'var(--wire)', color: 'var(--on)', border: 'none',
                    cursor: saveName.trim() ? 'pointer' : 'not-allowed', ...mono, fontSize: '0.6rem', letterSpacing: '0.1em', textTransform: 'uppercase', borderRadius: '2px',
                  }}>
                    <Save size={11} />{saving ? 'Saving…' : 'Save'}
                  </button>
                  {saveMsg && <span style={{ ...mono, fontSize: '0.6rem', color: saveMsg.includes('fail') ? 'var(--signal)' : 'var(--ok)' }}>{saveMsg}</span>}
                </div>
                <div style={{ ...mono, fontSize: '0.55rem', color: 'var(--on-low)', marginTop: '8px' }}>
                  Stores {visibleKpiIds.length} KPI{visibleKpiIds.length !== 1 ? 's' : ''} · {visibleGraphIndices.length} chart{visibleGraphIndices.length !== 1 ? 's' : ''}
                </div>
              </div>

              {/* List */}
              <div>
                <div style={{ ...mono, fontSize: '0.55rem', letterSpacing: '0.13em', textTransform: 'uppercase', color: 'var(--on-mid)', marginBottom: '10px' }}>
                  Saved Dashboards ({dashboards.length})
                </div>
                {dashboards.length === 0 && <p style={{ fontSize: '0.75rem', color: 'var(--on-low)' }}>No saved dashboards yet.</p>}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {dashboards.map(d => (
                    <div key={d.id} style={{ background: 'var(--surface-hi)', padding: '10px 12px', borderRadius: '2px', borderLeft: '2px solid var(--wire-hi)' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: '0.82rem', color: 'var(--on)', fontWeight: 500, marginBottom: '2px' }}>{d.name}</div>
                          {d.description && <div style={{ fontSize: '0.7rem', color: 'var(--on-low)', marginBottom: '3px' }}>{d.description}</div>}
                          <div style={{ ...mono, fontSize: '0.55rem', color: 'var(--on-low)' }}>
                            {d.created_by_name || d.created_by} · {d.visible_kpi_ids.length} KPIs · {d.graphs.length} charts
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                          <button onClick={() => handleLoad(d)} style={{
                            display: 'flex', alignItems: 'center', gap: '4px',
                            background: 'var(--action)', border: 'none', cursor: 'pointer', color: 'var(--on)',
                            padding: '4px 8px', borderRadius: '2px', ...mono, fontSize: '0.55rem', letterSpacing: '0.1em', textTransform: 'uppercase',
                          }}><Download size={10} /> Load</button>
                          {d.created_by === currentUserId && (
                            <button onClick={() => void handleDelete(d.id)} style={{
                              display: 'flex', alignItems: 'center', background: 'var(--surface-raise)',
                              border: '1px solid var(--wire)', cursor: 'pointer', color: 'var(--on-mid)', padding: '4px', borderRadius: '2px',
                            }}><Trash2 size={11} /></button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
