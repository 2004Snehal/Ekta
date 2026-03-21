'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Download, Trash2 } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
const USER_ID = process.env.NEXT_PUBLIC_DASHBOARD_USER_ID ?? 'demo-user';

interface TeamMember { id: string; name: string; profile: string; role: string; }
interface SavedDashboard {
  id: string; name: string; description?: string;
  created_by: string; created_by_name?: string;
  visible_kpi_ids: string[]; graphs: { source: string; index: number }[];
  created_at: string;
}

const PROFILE_LABELS: Record<string, string> = {
  founder: 'Founder', client_success: 'Client Success', operations: 'Operations',
  editorial: 'Editorial', tech_product: 'Tech & Product', team_member: 'Team Member',
  admin: 'Admin', user: 'User',
};

const PROFILE_COLOUR: Record<string, string> = {
  founder: 'var(--signal)', client_success: 'var(--uplink)', operations: 'var(--warn)',
  editorial: 'var(--ok)', tech_product: '#9b59b6', team_member: 'var(--on-mid)',
};

export default function WorkspacePage() {
  const router = useRouter();
  const [grouped, setGrouped]     = useState<Record<string, TeamMember[]>>({});
  const [dashboards, setDashboards] = useState<SavedDashboard[]>([]);
  const [tab, setTab]             = useState<'team' | 'dashboards'>('team');

  useEffect(() => {
    if (!API) return;
    fetch(`${API}/workspace/team`).then(r => r.ok ? r.json() : null).then(d => { if (d?.grouped) setGrouped(d.grouped); }).catch(() => {});
    fetch(`${API}/workspace/dashboards`).then(r => r.ok ? r.json() : null).then(d => { if (d?.dashboards) setDashboards(d.dashboards); }).catch(() => {});
  }, []);

  async function handleDelete(id: string) {
    await fetch(`${API}/workspace/dashboards/${id}?user_id=${encodeURIComponent(USER_ID)}`, { method: 'DELETE' }).catch(() => {});
    setDashboards(prev => prev.filter(d => d.id !== id));
  }

  const mono: React.CSSProperties = { fontFamily: 'var(--font-mono)' };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--void)', padding: '32px 40px' }}>
      <div style={{ marginBottom: '28px', borderBottom: '1px solid var(--wire)', paddingBottom: '16px' }}>
        <h1 style={{ ...mono, fontSize: '0.7rem', letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--on-mid)', margin: 0 }}>Workspace</h1>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--wire)', marginBottom: '28px' }}>
        {(['team', 'dashboards'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: '10px 24px', background: 'none', border: 'none', cursor: 'pointer',
            ...mono, fontSize: '0.6rem', letterSpacing: '0.14em', textTransform: 'uppercase',
            color: tab === t ? 'var(--on)' : 'var(--on-low)',
            borderBottom: tab === t ? '2px solid var(--signal)' : '2px solid transparent',
          }}>
            {t === 'team' ? 'Team Directory' : `Saved Dashboards (${dashboards.length})`}
          </button>
        ))}
      </div>

      {/* TEAM */}
      {tab === 'team' && (
        <div style={{ maxWidth: '900px', display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {Object.keys(grouped).length === 0 && <p style={{ fontSize: '0.8rem', color: 'var(--on-low)' }}>No team members found.</p>}
          {Object.entries(grouped).map(([profile, members]) => (
            <div key={profile}>
              <div style={{ ...mono, fontSize: '0.55rem', letterSpacing: '0.18em', textTransform: 'uppercase', color: PROFILE_COLOUR[profile] ?? 'var(--on-mid)', marginBottom: '12px' }}>
                {PROFILE_LABELS[profile] ?? profile} <span style={{ color: 'var(--on-low)' }}>({members.length})</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '10px' }}>
                {members.map(m => (
                  <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 14px', background: 'var(--surface)', border: '1px solid var(--wire)', borderRadius: '2px' }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
                      background: `color-mix(in srgb, ${PROFILE_COLOUR[profile] ?? 'var(--on-mid)'} 15%, transparent)`,
                      border: `1px solid ${PROFILE_COLOUR[profile] ?? 'var(--wire-hi)'}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      ...mono, fontSize: '0.7rem', color: PROFILE_COLOUR[profile] ?? 'var(--on-mid)',
                    }}>{(m.name || '?')[0].toUpperCase()}</div>
                    <div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--on)', fontWeight: 500 }}>{m.name}</div>
                      <div style={{ ...mono, fontSize: '0.55rem', color: 'var(--on-low)', marginTop: '2px' }}>{PROFILE_LABELS[m.profile] ?? m.profile}</div>
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
        <div style={{ maxWidth: '800px' }}>
          {dashboards.length === 0 && (
            <div style={{ padding: '32px', border: '1px dashed var(--wire)', borderRadius: '2px', textAlign: 'center' }}>
              <p style={{ ...mono, fontSize: '0.65rem', color: 'var(--on-low)', margin: 0 }}>
                No saved dashboards yet. Open Dashboard → click WORKSPACE ↗ → Dashboards tab → save.
              </p>
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {dashboards.map(d => (
              <div key={d.id} style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', padding: '14px 16px', background: 'var(--surface)', border: '1px solid var(--wire)', borderRadius: '2px' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '0.88rem', color: 'var(--on)', fontWeight: 600, marginBottom: '3px' }}>{d.name}</div>
                  {d.description && <div style={{ fontSize: '0.75rem', color: 'var(--on-low)', marginBottom: '5px' }}>{d.description}</div>}
                  <div style={{ ...mono, fontSize: '0.55rem', color: 'var(--on-low)' }}>
                    by {d.created_by_name || d.created_by}
                    <span style={{ margin: '0 6px', color: 'var(--wire-hi)' }}>·</span>
                    {d.visible_kpi_ids.length} KPIs · {d.graphs.length} charts
                    <span style={{ margin: '0 6px', color: 'var(--wire-hi)' }}>·</span>
                    {new Date(d.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                  <button onClick={() => router.push(`/dashboard?load_dashboard=${d.id}`)} style={{
                    display: 'flex', alignItems: 'center', gap: '5px',
                    background: 'var(--action)', border: 'none', cursor: 'pointer', color: 'var(--on)',
                    padding: '6px 14px', borderRadius: '2px', ...mono, fontSize: '0.6rem', letterSpacing: '0.1em', textTransform: 'uppercase',
                  }}><Download size={12} /> Load</button>
                  {d.created_by === USER_ID && (
                    <button onClick={() => void handleDelete(d.id)} style={{
                      display: 'flex', alignItems: 'center', background: 'var(--surface-hi)',
                      border: '1px solid var(--wire)', cursor: 'pointer', color: 'var(--on-mid)', padding: '6px 8px', borderRadius: '2px',
                    }}><Trash2 size={13} /></button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
