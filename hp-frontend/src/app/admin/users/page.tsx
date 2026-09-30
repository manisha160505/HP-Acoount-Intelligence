'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { useAuth } from '@/providers/AuthProvider';
import api from '@/services/api';
import { parseApiError } from '@/lib/apiError';
import { ManagedUser } from '@/types/analytics';
import {
  Users,
  UserPlus,
  Loader2,
  AlertCircle,
  CheckCircle2,
  X,
  RefreshCw,
  UserX,
  UserCheck,
} from 'lucide-react';

const EMPTY_FORM = { email: '', full_name: '', password: '' };

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  // Timestamps are stored in UTC; a naive one from the API is UTC too.
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  return isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fetchUsers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.get<ManagedUser[]>('/admin/users');
      setUsers(res.data);
    } catch (err) {
      setError(parseApiError(err, 'Failed to load users.').message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const openModal = () => {
    setForm(EMPTY_FORM);
    setFormError(null);
    setFieldErrors({});
    setIsModalOpen(true);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFieldErrors({});

    const payload = { email: form.email.trim(), full_name: form.full_name.trim(), password: form.password };
    const localErrors: Record<string, string> = {};
    if (!payload.full_name) localErrors.full_name = 'Name is required.';
    if (!/^\S+@\S+\.\S+$/.test(payload.email)) localErrors.email = 'Enter a valid email address.';
    if (payload.password.length < 8) localErrors.password = 'At least 8 characters.';
    if (Object.keys(localErrors).length) {
      setFieldErrors(localErrors);
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await api.post<ManagedUser>('/admin/users', payload);
      setUsers(prev => [...prev, res.data]);
      setIsModalOpen(false);
      // The temporary password is not echoed back; the admin already has it.
      setForm(EMPTY_FORM);
      setSuccessMsg(`User ${res.data.email} created. Share the temporary password with them directly.`);
    } catch (err) {
      const parsed = parseApiError(err, 'Could not create the user.');
      if (parsed.code === 'ALREADY_EXISTS') {
        setFieldErrors({ email: 'A user with this email already exists.' });
      } else {
        setFieldErrors(parsed.fields);
      }
      setFormError(parsed.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleToggle = async (target: ManagedUser) => {
    setTogglingId(target.id);
    setError(null);
    try {
      const res = await api.patch<ManagedUser>(`/admin/users/${target.id}`, { is_active: !target.is_active });
      setUsers(prev => prev.map(u => (u.id === target.id ? res.data : u)));
      setSuccessMsg(`${res.data.email} is now ${res.data.is_active ? 'active' : 'deactivated'}.`);
    } catch (err) {
      setError(parseApiError(err, 'Could not update the user.').message);
    } finally {
      setTogglingId(null);
    }
  };

  const inputClass = (field: string) =>
    `block w-full px-3.5 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-hp-navy text-sm font-medium bg-gray-50 focus:bg-white transition ${
      fieldErrors[field] ? 'border-red-400' : 'border-gray-300'
    }`;

  return (
    <ProtectedRoute allowedRoles={['admin']}>
      <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">

        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-extrabold text-gray-900 tracking-tight flex items-center gap-2">
              <Users className="w-7 h-7 text-hp-navy" />
              <span>Users</span>
            </h1>
            <p className="text-xs text-gray-500 mt-1 font-medium">
              Add sellers and control who can sign in. Deactivated users keep their usage history.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={fetchUsers}
              className="p-2.5 text-gray-500 hover:text-hp-navy rounded-lg hover:bg-gray-100 transition"
              title="Refresh user list"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={openModal}
              className="inline-flex items-center justify-center px-4 py-2.5 border border-transparent rounded-lg shadow-md text-sm font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-hp-navy transition duration-150"
            >
              <UserPlus className="w-4 h-4 mr-2" />
              <span>Add User</span>
            </button>
          </div>
        </div>

        {successMsg && (
          <div className="mb-6 bg-emerald-50 border-l-4 border-emerald-500 p-4 rounded-r-lg flex items-center justify-between text-emerald-800 text-xs font-semibold shadow-sm">
            <div className="flex items-center space-x-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
              <span>{successMsg}</span>
            </div>
            <button onClick={() => setSuccessMsg(null)}>
              <X className="w-4 h-4 text-emerald-600" />
            </button>
          </div>
        )}

        {error && (
          <div className="mb-6 bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg flex items-center justify-between text-red-800 text-xs font-semibold shadow-sm">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
              <span>{error}</span>
            </div>
            <button onClick={() => setError(null)}>
              <X className="w-4 h-4 text-red-600" />
            </button>
          </div>
        )}

        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="p-12 flex flex-col items-center justify-center space-y-3">
              <Loader2 className="w-8 h-8 text-hp-navy animate-spin" />
              <p className="text-xs text-gray-500 font-medium">Loading users...</p>
            </div>
          ) : users.length === 0 ? (
            <div className="p-12 text-center">
              <Users className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <h3 className="text-sm font-bold text-gray-800">No users yet</h3>
              <p className="text-xs text-gray-500 mt-1">Add the first seller with the Add User button.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200 text-[11px] font-bold uppercase tracking-wider text-gray-600">
                    <th className="py-3.5 px-6">Name</th>
                    <th className="py-3.5 px-6">Email</th>
                    <th className="py-3.5 px-6">Role</th>
                    <th className="py-3.5 px-6">Status</th>
                    <th className="py-3.5 px-6">Created</th>
                    <th className="py-3.5 px-6">Last Login</th>
                    <th className="py-3.5 px-6 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 text-xs font-medium">
                  {users.map(u => {
                    const isSelf = u.id === currentUser?.id;
                    return (
                      <tr key={u.id} className="hover:bg-slate-50/80 transition duration-150">
                        <td className="py-4 px-6 text-sm text-gray-900 font-bold">{u.full_name || '—'}</td>
                        <td className="py-4 px-6 text-gray-700">{u.email}</td>
                        <td className="py-4 px-6">
                          <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-bold capitalize ${
                            u.role === 'admin' ? 'bg-hp-navy/10 text-hp-navy' : 'bg-gray-100 text-gray-700'
                          }`}>
                            {u.role}
                          </span>
                        </td>
                        <td className="py-4 px-6">
                          {u.is_active ? (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5"></span>
                              Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-gray-100 text-gray-600 border border-gray-200">
                              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 mr-1.5"></span>
                              Deactivated
                            </span>
                          )}
                        </td>
                        <td className="py-4 px-6 text-gray-500">{formatDateTime(u.created_at)}</td>
                        <td className="py-4 px-6 text-gray-500">{u.last_login_at ? formatDateTime(u.last_login_at) : 'Never'}</td>
                        <td className="py-4 px-6 text-right">
                          {isSelf ? (
                            <span className="text-[11px] text-gray-400">You</span>
                          ) : (
                            <button
                              type="button"
                              disabled={togglingId === u.id}
                              onClick={() => handleToggle(u)}
                              className={`inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-bold transition disabled:opacity-60 ${
                                u.is_active
                                  ? 'bg-amber-50 text-amber-700 hover:bg-amber-600 hover:text-white border border-amber-200'
                                  : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-600 hover:text-white border border-emerald-200'
                              }`}
                            >
                              {togglingId === u.id ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : u.is_active ? (
                                <>
                                  <UserX className="w-3.5 h-3.5" />
                                  <span>Deactivate</span>
                                </>
                              ) : (
                                <>
                                  <UserCheck className="w-3.5 h-3.5" />
                                  <span>Activate</span>
                                </>
                              )}
                            </button>
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
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden border border-gray-200">
            <div className="flex justify-between items-center px-6 py-4 bg-gray-50 border-b border-gray-200">
              <h3 className="text-base font-bold text-gray-900 flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-hp-navy" />
                <span>Add User</span>
              </h3>
              <button type="button" onClick={() => setIsModalOpen(false)} className="text-gray-400 hover:text-gray-600 rounded-lg p-1">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreate} noValidate className="p-6 space-y-4">
              {formError && (
                <div className="bg-red-50 border-l-4 border-red-500 p-3 rounded-r-lg flex items-center space-x-2 text-xs font-medium text-red-700">
                  <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                  <span>{formError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                  Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  autoFocus
                  value={form.full_name}
                  onChange={e => setForm({ ...form, full_name: e.target.value })}
                  placeholder="e.g. Priya Sharma"
                  className={inputClass('full_name')}
                />
                {fieldErrors.full_name && <p className="text-[11px] text-red-600 mt-1">{fieldErrors.full_name}</p>}
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                  Email <span className="text-red-500">*</span>
                </label>
                <input
                  type="email"
                  value={form.email}
                  onChange={e => setForm({ ...form, email: e.target.value })}
                  placeholder="name@company.com"
                  className={inputClass('email')}
                />
                {fieldErrors.email && <p className="text-[11px] text-red-600 mt-1">{fieldErrors.email}</p>}
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                  Temporary Password <span className="text-red-500">*</span>
                </label>
                <input
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={e => setForm({ ...form, password: e.target.value })}
                  className={inputClass('password')}
                />
                {fieldErrors.password ? (
                  <p className="text-[11px] text-red-600 mt-1">{fieldErrors.password}</p>
                ) : (
                  <p className="text-[11px] text-gray-500 mt-1">At least 8 characters. The user is created with role “user”.</p>
                )}
              </div>

              <div className="flex justify-end space-x-3 pt-4 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-xs font-bold text-gray-600 hover:text-gray-800 bg-gray-100 hover:bg-gray-200 rounded-lg transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="inline-flex items-center justify-center px-4 py-2 border border-transparent rounded-lg shadow-sm text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none transition disabled:opacity-50"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                      <span>Creating...</span>
                    </>
                  ) : (
                    <span>Create User</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </ProtectedRoute>
  );
}
