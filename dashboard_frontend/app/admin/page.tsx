'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { apiListUsers, apiUpdateUser, type AuthUser } from '@/lib/auth';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Loader2, Users, ShieldCheck, User, Check, AlertCircle } from 'lucide-react';

type UserRow = AuthUser & { created_at: string };

const PROFILES = ['team_member', 'founder', 'editor', 'manager', 'analyst'] as const;
const PROFILE_LABELS: Record<string, string> = {
  team_member: 'Team Member',
  founder: 'Founder',
  editor: 'Editor',
  manager: 'Manager',
  analyst: 'Analyst',
};

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

export default function AdminPage() {
  const { user, token, loading: authLoading } = useAuth();
  const router = useRouter();

  const [users, setUsers] = useState<UserRow[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [error, setError] = useState('');
  // Per-row pending edits: { [userId]: { role?, profile? } }
  const [edits, setEdits] = useState<Record<string, { role?: string; profile?: string }>>({});
  const [saveStates, setSaveStates] = useState<Record<string, SaveState>>({});

  // Redirect non-admins
  useEffect(() => {
    if (!authLoading && (!user || user.role !== 'admin')) {
      router.replace('/dashboard');
    }
  }, [authLoading, user, router]);

  useEffect(() => {
    if (!token || !user || user.role !== 'admin') return;
    setLoadingUsers(true);
    apiListUsers(token)
      .then(setUsers)
      .catch((e) => setError(e.message))
      .finally(() => setLoadingUsers(false));
  }, [token, user]);

  function setEdit(userId: string, field: 'role' | 'profile', value: string) {
    setEdits((prev) => ({
      ...prev,
      [userId]: { ...prev[userId], [field]: value },
    }));
    setSaveStates((prev) => ({ ...prev, [userId]: 'idle' }));
  }

  async function saveUser(userId: string) {
    const update = edits[userId];
    if (!update || !token) return;
    setSaveStates((prev) => ({ ...prev, [userId]: 'saving' }));
    try {
      const updated = await apiUpdateUser(token, userId, update);
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, ...updated } : u)));
      setEdits((prev) => { const n = { ...prev }; delete n[userId]; return n; });
      setSaveStates((prev) => ({ ...prev, [userId]: 'saved' }));
      setTimeout(() => setSaveStates((prev) => ({ ...prev, [userId]: 'idle' })), 2000);
    } catch (e) {
      setSaveStates((prev) => ({ ...prev, [userId]: 'error' }));
    }
  }

  if (authLoading || (!user && !authLoading)) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (user?.role !== 'admin') return null;

  const adminCount = users.filter((u) => u.role === 'admin').length;
  const userCount = users.filter((u) => u.role === 'user').length;

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-foreground">Admin Panel</h1>
        <p className="text-muted-foreground mt-1">Manage user roles and profiles</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="bg-card border-border">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-primary/15 rounded-lg flex items-center justify-center">
                <Users className="w-5 h-5 text-primary" />
              </div>
              <div>
                <p className="text-2xl font-bold">{users.length}</p>
                <p className="text-xs text-muted-foreground">Total Users</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-yellow-500/15 rounded-lg flex items-center justify-center">
                <ShieldCheck className="w-5 h-5 text-yellow-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{adminCount}</p>
                <p className="text-xs text-muted-foreground">Admins</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-500/15 rounded-lg flex items-center justify-center">
                <User className="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{userCount}</p>
                <p className="text-xs text-muted-foreground">Members</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* User Table */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>Users</CardTitle>
          <CardDescription>
            Change roles and profiles. The first registered account is always admin.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && (
            <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-md px-3 py-2 mb-4">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {loadingUsers ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-muted-foreground text-left">
                    <th className="pb-3 font-medium">Name</th>
                    <th className="pb-3 font-medium">Email</th>
                    <th className="pb-3 font-medium">Role</th>
                    <th className="pb-3 font-medium">Profile</th>
                    <th className="pb-3 font-medium">Joined</th>
                    <th className="pb-3 font-medium"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {users.map((u) => {
                    const pendingEdit = edits[u.id] ?? {};
                    const currentRole = pendingEdit.role ?? u.role;
                    const currentProfile = pendingEdit.profile ?? u.profile;
                    const isDirty = !!edits[u.id];
                    const saveState = saveStates[u.id] ?? 'idle';
                    const isMe = u.id === user.id;

                    return (
                      <tr key={u.id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-3 pr-4">
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-xs font-semibold text-primary">
                              {u.name.charAt(0).toUpperCase()}
                            </div>
                            <span className="font-medium text-foreground">
                              {u.name}
                              {isMe && (
                                <span className="ml-1.5 text-xs text-muted-foreground">(you)</span>
                              )}
                            </span>
                          </div>
                        </td>
                        <td className="py-3 pr-4 text-muted-foreground">{u.email}</td>
                        <td className="py-3 pr-4">
                          <Select
                            value={currentRole}
                            onValueChange={(v) => setEdit(u.id, 'role', v)}
                          >
                            <SelectTrigger className="w-28 h-8 text-xs bg-background">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="user">User</SelectItem>
                              <SelectItem value="admin">Admin</SelectItem>
                            </SelectContent>
                          </Select>
                        </td>
                        <td className="py-3 pr-4">
                          <Select
                            value={currentProfile}
                            onValueChange={(v) => setEdit(u.id, 'profile', v)}
                          >
                            <SelectTrigger className="w-36 h-8 text-xs bg-background">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {PROFILES.map((p) => (
                                <SelectItem key={p} value={p}>
                                  {PROFILE_LABELS[p]}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </td>
                        <td className="py-3 pr-4 text-muted-foreground text-xs">
                          {new Date(u.created_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                          })}
                        </td>
                        <td className="py-3">
                          {saveState === 'saved' ? (
                            <span className="flex items-center gap-1 text-xs text-green-500">
                              <Check className="w-3.5 h-3.5" /> Saved
                            </span>
                          ) : saveState === 'error' ? (
                            <span className="flex items-center gap-1 text-xs text-destructive">
                              <AlertCircle className="w-3.5 h-3.5" /> Error
                            </span>
                          ) : (
                            <Button
                              size="sm"
                              variant={isDirty ? 'default' : 'ghost'}
                              className="h-8 text-xs px-3"
                              disabled={!isDirty || saveState === 'saving'}
                              onClick={() => saveUser(u.id)}
                            >
                              {saveState === 'saving' ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                'Save'
                              )}
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
