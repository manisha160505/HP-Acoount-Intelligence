'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { PageHero } from '@/components/common/motion';
import { useAuth } from '@/providers/AuthProvider';
import { isAdminRole } from '@/types/auth';
import api from '@/services/api';
import { parseApiError } from '@/lib/apiError';
import type { CreatedUser, ManagedUser } from '@/types/analytics';
import type { CompanyAccount } from '@/types/account';
import { Modal, ModalActions, dangerButton, primaryButton, secondaryButton } from '@/components/users/Modal';
import { AccountPicker } from '@/components/users/AccountPicker';
import { OneTimePassword } from '@/components/users/OneTimePassword';
import { AuditLog, formatDateTime } from '@/components/users/AuditLog';
import { ROW_BUTTON, RowMenu } from '@/components/common/RowMenu';
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  KeyRound,
  Loader2,
  LogOut,
  RefreshCw,
  Search,
  ShieldCheck,
  UserCheck,
  UserPlus,
  Users,
  UserX,
  X,
} from 'lucide-react';

type Dialog =
  | { kind: 'create' }
  | { kind: 'accounts'; user: ManagedUser }
  | { kind: 'reset'; user: ManagedUser }
  | { kind: 'role'; user: ManagedUser }
  | { kind: 'active'; user: ManagedUser }
  | { kind: 'credentials'; email: string; password: string; title: string }
  | { kind: 'signOutAll' };

const ROLE_LABEL: Record<string, string> = { super_admin: 'Super admin', admin: 'Admin', user: 'User' };

export default function AdminUsersPage() {
  const { user: me } = useAuth();
  const isSuper = me?.role === 'super_admin';

  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [accounts, setAccounts] = useState<CompanyAccount[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [tab, setTab] = useState<'users' | 'activity'>('users');
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState<'all' | 'user' | 'admin' | 'none'>('all');
  const [dialog, setDialog] = useState<Dialog | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [u, a] = await Promise.all([
        api.get<ManagedUser[]>('/admin/users'),
        api.get<CompanyAccount[]>('/accounts'),
      ]);
      setUsers(u.data);
      setAccounts([...a.data].sort((x, y) => x.name.localeCompare(y.name)));
    } catch (err) {
      setError(parseApiError(err, 'Failed to load users.').message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const accountName = useMemo(() => new Map(accounts.map((a) => [a.id, a.name])), [accounts]);

  const replace = (next: ManagedUser) => setUsers((prev) => prev.map((u) => (u.id === next.id ? next : u)));

  /** Mirrors the server's rules, to hide what would be refused. */
  const canManage = (target: ManagedUser) =>
    !!me && target.id !== me.id && target.role !== 'super_admin'
    && (!isAdminRole(target.role) || isSuper);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return users.filter((u) => {
      if (q && !u.email.toLowerCase().includes(q) && !u.full_name.toLowerCase().includes(q)) return false;
      if (roleFilter === 'user') return u.role === 'user';
      if (roleFilter === 'admin') return isAdminRole(u.role);
      if (roleFilter === 'none') return u.role === 'user' && u.account_ids.length === 0;
      return true;
    });
  }, [users, query, roleFilter]);

  const sellersWithoutAccounts = users.filter((u) => u.role === 'user' && u.is_active && u.account_ids.length === 0).length;

  return (
    <ProtectedRoute allowedRoles={['admin']}>
      <div className="as-page">
        <PageHero
          title="Users"
          subtitle="Add people, choose which accounts each seller can open, and reset passwords. Admins see every account."
          actions={
            <>
              <button type="button" onClick={load} title="Refresh"
                      className="p-2.5 text-slate-300 hover:text-white rounded-lg hover:bg-white/10 transition">
                <RefreshCw className="w-4 h-4" />
              </button>
              {isSuper && (
                <button type="button" onClick={() => setDialog({ kind: 'signOutAll' })}
                        className="inline-flex items-center px-3.5 py-2.5 rounded-lg text-sm font-bold text-slate-200 hover:text-white hover:bg-white/10 transition">
                  <LogOut className="w-4 h-4 mr-2" /> Sign out everyone
                </button>
              )}
              <button type="button" onClick={() => setDialog({ kind: 'create' })}
                      className="inline-flex items-center justify-center px-4 py-2.5 rounded-lg shadow-md text-sm font-bold text-white bg-hp-navy hover:bg-hp-blue transition">
                <UserPlus className="w-4 h-4 mr-2" /> Add user
              </button>
            </>
          }
        />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 -mt-12 sm:-mt-14 pb-12 space-y-5">
          {notice && (
            <div className="bg-emerald-50 as-fade border border-emerald-200 p-4 rounded-xl flex items-center justify-between text-emerald-800 text-xs font-semibold shadow-sm">
              <span className="flex items-center gap-2"><CheckCircle2 className="w-5 h-5 text-emerald-600" />{notice}</span>
              <button type="button" aria-label="Dismiss" onClick={() => setNotice(null)}><X className="w-4 h-4" /></button>
            </div>
          )}
          {error && (
            <div className="bg-red-50 as-fade border border-red-200 p-4 rounded-xl flex items-center justify-between text-red-800 text-xs font-semibold shadow-sm">
              <span className="flex items-center gap-2"><AlertCircle className="w-5 h-5 text-red-500" />{error}</span>
              <button type="button" aria-label="Dismiss" onClick={() => setError(null)}><X className="w-4 h-4" /></button>
            </div>
          )}

          <div className="flex gap-1 bg-white rounded-xl border border-gray-200 p-1 w-fit shadow-sm" role="tablist">
            {(['users', 'activity'] as const).map((t) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                      className={`px-4 py-1.5 rounded-lg text-xs font-bold transition ${tab === t ? 'bg-hp-navy text-white' : 'text-gray-600 hover:bg-gray-100'}`}>
                {t === 'users' ? `People (${users.length})` : 'Activity log'}
              </button>
            ))}
          </div>

          {tab === 'activity' ? (
            <AuditLog users={users} />
          ) : (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="flex flex-col md:flex-row md:items-center gap-3 justify-between px-5 py-3.5 border-b border-gray-200 bg-gray-50">
                <div className="relative md:w-80">
                  <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                  <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
                         placeholder="Search by email or name" aria-label="Search users"
                         className="w-full pl-8 pr-3 py-2 text-xs border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-hp-navy" />
                </div>
                <div className="flex items-center gap-1 text-[11px]">
                  {([['all', 'All'], ['user', 'Sellers'], ['admin', 'Admins'], ['none', `No accounts (${sellersWithoutAccounts})`]] as const).map(([v, label]) => (
                    <button key={v} type="button" onClick={() => setRoleFilter(v)}
                            className={`px-2.5 py-1 rounded-md font-bold ${roleFilter === v ? 'bg-hp-navy/10 text-hp-navy' : 'text-gray-500 hover:bg-gray-100'}`}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {isLoading ? (
                <div className="p-12 flex flex-col items-center gap-3">
                  <Loader2 className="w-8 h-8 text-hp-navy animate-spin" />
                  <p className="text-xs text-gray-500 font-medium">Loading users...</p>
                </div>
              ) : shown.length === 0 ? (
                <div className="p-12 text-center">
                  <Users className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-sm font-bold text-gray-800">{users.length ? 'No users match.' : 'No users yet'}</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-gray-200 text-[11px] font-bold uppercase tracking-wider text-gray-600">
                        <th className="py-3 px-5">User</th>
                        <th className="py-3 px-5">Role</th>
                        <th className="py-3 px-5">Accounts</th>
                        <th className="py-3 px-5">Status</th>
                        <th className="py-3 px-5">Last sign-in</th>
                        <th className="py-3 px-5 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 text-xs">
                      {shown.map((u) => {
                        const names = u.account_ids.map((id) => accountName.get(id) || id);
                        const manageable = canManage(u);
                        return (
                          <tr key={u.id} className="hover:bg-slate-50/80 align-top">
                            <td className="py-3.5 px-5 min-w-[220px]">
                              <div className="text-sm font-bold text-gray-900 break-words">{u.email}</div>
                              {u.full_name && u.full_name !== u.email && (
                                <div className="text-[11px] text-gray-500">{u.full_name}</div>
                              )}
                            </td>
                            <td className="py-3.5 px-5">
                              <span className={`inline-flex whitespace-nowrap px-2 py-0.5 rounded-full text-[11px] font-bold ${
                                isAdminRole(u.role) ? 'bg-hp-navy/10 text-hp-navy' : 'bg-gray-100 text-gray-700'}`}>
                                {ROLE_LABEL[u.role] || u.role}
                              </span>
                            </td>
                            <td className="py-3.5 px-5 max-w-xs">
                              {isAdminRole(u.role) ? (
                                <span className="text-gray-500">All accounts</span>
                              ) : names.length === 0 ? (
                                <span className="text-amber-700 font-semibold">None assigned</span>
                              ) : (
                                <span className="text-gray-700" title={names.join(', ')}>
                                  <span className="font-bold">{names.length}</span>
                                  {' · '}{names.slice(0, 2).join(', ')}{names.length > 2 ? `, +${names.length - 2} more` : ''}
                                </span>
                              )}
                            </td>
                            <td className="py-3.5 px-5 space-y-1">
                              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold border ${
                                u.is_active ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-gray-100 text-gray-600 border-gray-200'}`}>
                                {u.is_active ? 'Active' : 'Deactivated'}
                              </span>
                              {u.must_change_password && u.is_active && (
                                <div className="text-[11px] text-amber-700">Has not set a password yet</div>
                              )}
                            </td>
                            <td className="py-3.5 px-5 text-gray-500 whitespace-nowrap">
                              {u.last_login_at ? formatDateTime(u.last_login_at) : 'Never'}
                            </td>
                            <td className="py-3.5 px-5">
                              {u.id === me?.id ? (
                                <div className="text-right text-[11px] text-gray-400">You</div>
                              ) : !manageable ? (
                                <div className="text-right text-[11px] text-gray-400"
                                     title={u.role === 'super_admin'
                                       ? 'The super admin cannot be changed here.'
                                       : 'Only the super admin can manage admins.'}>
                                  {u.role === 'super_admin' ? '—' : 'Super admin only'}
                                </div>
                              ) : (
                                <div className="flex items-center justify-end gap-2">
                                  {u.role === 'user' && (
                                    <button type="button" onClick={() => setDialog({ kind: 'accounts', user: u })}
                                            className={ROW_BUTTON}>
                                      <Building2 className="w-3.5 h-3.5 text-gray-400" />
                                      Accounts
                                    </button>
                                  )}
                                  <RowMenu
                                    label={`Actions for ${u.email}`}
                                    items={[
                                      { label: 'Reset password', icon: <KeyRound className="w-3.5 h-3.5" />,
                                        onSelect: () => setDialog({ kind: 'reset', user: u }) },
                                      ...(isSuper ? [{
                                        label: u.role === 'admin' ? 'Make seller' : 'Make admin',
                                        icon: <ShieldCheck className="w-3.5 h-3.5" />,
                                        onSelect: () => setDialog({ kind: 'role', user: u }),
                                      }] : []),
                                      u.is_active
                                        ? { label: 'Deactivate', icon: <UserX className="w-3.5 h-3.5" />, danger: true,
                                            onSelect: () => setDialog({ kind: 'active', user: u }) }
                                        : { label: 'Activate', icon: <UserCheck className="w-3.5 h-3.5" />,
                                            onSelect: () => setDialog({ kind: 'active', user: u }) },
                                    ]}
                                  />
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>

        {dialog?.kind === 'create' && (
          <CreateUserDialog
            isSuper={isSuper}
            accounts={accounts}
            onClose={() => setDialog(null)}
            onCreated={(created) => {
              setUsers((prev) => [...prev, created]);
              if (created.temporary_password) {
                setDialog({ kind: 'credentials', email: created.email, password: created.temporary_password,
                            title: 'User created' });
              } else {
                setDialog(null);
                setNotice(`${created.email} created. Share the password you set with them directly.`);
              }
            }}
          />
        )}
        {dialog?.kind === 'accounts' && (
          <AccountsDialog user={dialog.user} accounts={accounts} onClose={() => setDialog(null)}
                          onSaved={(u) => { replace(u); setDialog(null); setNotice(`Accounts updated for ${u.email}.`); }} />
        )}
        {dialog?.kind === 'reset' && (
          <ResetPasswordDialog user={dialog.user} onClose={() => setDialog(null)}
                               onDone={(u, pw) => {
                                 replace(u);
                                 if (pw) setDialog({ kind: 'credentials', email: u.email, password: pw, title: 'Password reset' });
                                 else { setDialog(null); setNotice(`Password reset for ${u.email}.`); }
                               }} />
        )}
        {dialog?.kind === 'role' && (
          <ConfirmDialog
            title={dialog.user.role === 'admin' ? 'Make seller' : 'Make admin'}
            body={dialog.user.role === 'admin'
              ? `${dialog.user.email} will see only the accounts assigned to them and lose access to the admin pages.`
              : `${dialog.user.email} will see every account and get access to the admin pages, including Users, Rules and Regeneration.`}
            confirm={dialog.user.role === 'admin' ? 'Make seller' : 'Make admin'}
            onClose={() => setDialog(null)}
            run={async () => {
              const target = dialog.user;
              const res = await api.put<ManagedUser>(`/admin/users/${target.id}/role`,
                                                     { role: target.role === 'admin' ? 'user' : 'admin' });
              replace(res.data);
              setNotice(`${res.data.email} is now ${ROLE_LABEL[res.data.role].toLowerCase()}.`);
            }}
          />
        )}
        {dialog?.kind === 'active' && (
          <ConfirmDialog
            title={dialog.user.is_active ? 'Deactivate user' : 'Activate user'}
            body={dialog.user.is_active
              ? `${dialog.user.email} will be signed out at once and will not be able to sign in. Their history is kept.`
              : `${dialog.user.email} will be able to sign in again with their existing password.`}
            confirm={dialog.user.is_active ? 'Deactivate' : 'Activate'}
            danger={dialog.user.is_active}
            onClose={() => setDialog(null)}
            run={async () => {
              const target = dialog.user;
              const res = await api.patch<ManagedUser>(`/admin/users/${target.id}`, { is_active: !target.is_active });
              replace(res.data);
              setNotice(`${res.data.email} is now ${res.data.is_active ? 'active' : 'deactivated'}.`);
            }}
          />
        )}
        {dialog?.kind === 'signOutAll' && (
          <ConfirmDialog
            title="Sign out everyone"
            body="Every other session ends at once. Everyone, admins included, will have to sign in again. You stay signed in."
            confirm="Sign out everyone"
            danger
            onClose={() => setDialog(null)}
            run={async () => {
              const res = await api.post<{ message: string }>('/auth/sessions/revoke-all');
              setNotice(res.data.message);
            }}
          />
        )}
        {dialog?.kind === 'credentials' && (
          <Modal title={dialog.title} icon={<KeyRound className="w-5 h-5 text-hp-navy" />} onClose={() => setDialog(null)}>
            <div className="p-6 space-y-4">
              <OneTimePassword email={dialog.email} password={dialog.password} />
              <ModalActions>
                <button type="button" className={primaryButton} onClick={() => setDialog(null)}>I have copied it</button>
              </ModalActions>
            </div>
          </Modal>
        )}
      </div>
    </ProtectedRoute>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">{children}</label>;
}

function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="bg-red-50 border border-red-200 p-3 rounded-xl flex items-center gap-2 text-xs font-medium text-red-700">
      <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" /><span>{message}</span>
    </div>
  );
}

const inputClass = (bad?: string) =>
  `block w-full px-3.5 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-hp-navy text-sm bg-gray-50 focus:bg-white transition ${bad ? 'border-red-400' : 'border-gray-300'}`;

function CreateUserDialog({ isSuper, accounts, onClose, onCreated }: {
  isSuper: boolean;
  accounts: CompanyAccount[];
  onClose: () => void;
  onCreated: (u: CreatedUser) => void;
}) {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState<'user' | 'admin'>('user');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) local.email = 'Enter a valid email address.';
    setFields(local);
    setError(null);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      const res = await api.post<CreatedUser>('/admin/users', {
        email: email.trim(),
        ...(name.trim() ? { full_name: name.trim() } : {}),
        role,
        account_ids: role === 'user' ? Array.from(selected) : [],
      });
      onCreated(res.data);
    } catch (err) {
      const parsed = parseApiError(err, 'Could not create the user.');
      setFields(parsed.code === 'ALREADY_EXISTS' ? { email: 'A user with this email already exists.' } : parsed.fields);
      setError(parsed.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Add user" icon={<UserPlus className="w-5 h-5 text-hp-navy" />} onClose={onClose} wide>
      <form onSubmit={submit} noValidate className="p-6 space-y-4">
        <FormError message={error} />
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <FieldLabel>Email <span className="text-red-500">*</span></FieldLabel>
            <input type="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)}
                   placeholder="name@hp.com" className={inputClass(fields.email)} />
            {fields.email && <p className="text-[11px] text-red-600 mt-1">{fields.email}</p>}
          </div>
          <div>
            <FieldLabel>Name</FieldLabel>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)}
                   placeholder="Optional - the email is used if empty" className={inputClass()} />
          </div>
        </div>

        {isSuper && (
          <div>
            <FieldLabel>Role</FieldLabel>
            <div className="flex gap-2">
              {(['user', 'admin'] as const).map((r) => (
                <button key={r} type="button" onClick={() => setRole(r)}
                        className={`flex-1 px-3 py-2 rounded-lg border text-xs font-bold ${role === r ? 'border-hp-navy bg-hp-navy/5 text-hp-navy' : 'border-gray-200 text-gray-600'}`}>
                  {r === 'user' ? 'Seller - assigned accounts only' : 'Admin - every account and admin pages'}
                </button>
              ))}
            </div>
          </div>
        )}

        {role === 'user' && (
          <div>
            <FieldLabel>Accounts</FieldLabel>
            <AccountPicker accounts={accounts} selected={selected} onChange={setSelected} />
            {fields.account_ids && <p className="text-[11px] text-red-600 mt-1">{fields.account_ids}</p>}
            {selected.size === 0 && (
              <p className="text-[11px] text-gray-500 mt-1">With no accounts they will see “no accounts assigned” until you add some.</p>
            )}
          </div>
        )}

        <div className="flex items-start gap-2.5 rounded-xl bg-slate-50 border border-slate-200 p-3">
          <KeyRound className="w-4 h-4 text-hp-navy mt-0.5 flex-shrink-0" />
          <p className="text-[11px] text-gray-600 leading-relaxed">
            A temporary password is generated and shown once, after you create the user, for you to
            copy and share. No email is sent; they set their own password at first sign-in.
          </p>
        </div>

        <ModalActions>
          <button type="button" onClick={onClose} className={secondaryButton}>Cancel</button>
          <button type="submit" disabled={busy} className={primaryButton}>
            {busy ? <><Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />Creating...</> : 'Create user'}
          </button>
        </ModalActions>
      </form>
    </Modal>
  );
}

function AccountsDialog({ user, accounts, onClose, onSaved }: {
  user: ManagedUser; accounts: CompanyAccount[]; onClose: () => void; onSaved: (u: ManagedUser) => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set(user.account_ids));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.put<ManagedUser>(`/admin/users/${user.id}/accounts`, { account_ids: Array.from(selected) });
      onSaved(res.data);
    } catch (err) {
      setError(parseApiError(err, 'Could not save the accounts.').message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={`Accounts for ${user.email}`} icon={<Building2 className="w-5 h-5 text-hp-navy" />} onClose={onClose} wide>
      <div className="p-6 space-y-4">
        <FormError message={error} />
        <AccountPicker accounts={accounts} selected={selected} onChange={setSelected} />
        <p className="text-[11px] text-gray-500">Changes apply on their next click; a removed account closes for them at once.</p>
        <ModalActions>
          <button type="button" onClick={onClose} className={secondaryButton}>Cancel</button>
          <button type="button" onClick={save} disabled={busy} className={primaryButton}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : `Save ${selected.size} account${selected.size === 1 ? '' : 's'}`}
          </button>
        </ModalActions>
      </div>
    </Modal>
  );
}

function ResetPasswordDialog({ user, onClose, onDone }: {
  user: ManagedUser; onClose: () => void; onDone: (u: ManagedUser, password: string | null) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reset = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<{ user: ManagedUser; temporary_password: string | null }>(
        `/admin/users/${user.id}/reset-password`, {});
      onDone(res.data.user, res.data.temporary_password);
    } catch (err) {
      setError(parseApiError(err, 'Could not reset the password.').message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Reset password" icon={<KeyRound className="w-5 h-5 text-hp-navy" />} onClose={onClose}>
      <div className="p-6 space-y-4">
        <FormError message={error} />
        <p className="text-sm text-gray-700">
          A new temporary password is generated for <span className="font-bold">{user.email}</span>.
          They are signed out everywhere and must set their own password at next sign-in.
        </p>
        <ModalActions>
          <button type="button" onClick={onClose} className={secondaryButton}>Cancel</button>
          <button type="button" onClick={reset} disabled={busy} className={primaryButton}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Generate new password'}
          </button>
        </ModalActions>
      </div>
    </Modal>
  );
}

function ConfirmDialog({ title, body, confirm, danger = false, onClose, run }: {
  title: string; body: string; confirm: string; danger?: boolean; onClose: () => void; run: () => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      await run();
      onClose();
    } catch (err) {
      setError(parseApiError(err, 'That did not work.').message);
      setBusy(false);
    }
  };
  return (
    <Modal title={title} onClose={onClose}>
      <div className="p-6 space-y-4">
        <FormError message={error} />
        <p className="text-sm text-gray-700">{body}</p>
        <ModalActions>
          <button type="button" onClick={onClose} className={secondaryButton}>Cancel</button>
          <button type="button" onClick={go} disabled={busy} className={danger ? dangerButton : primaryButton}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : confirm}
          </button>
        </ModalActions>
      </div>
    </Modal>
  );
}
