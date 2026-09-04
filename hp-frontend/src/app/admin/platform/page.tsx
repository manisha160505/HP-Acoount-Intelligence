'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import api from '@/services/api';
import { CompanyAccount, AccountStatus } from '@/types/account';
import { 
  Building2, 
  Plus, 
  Search, 
  Eye, 
  EyeOff, 
  Settings2, 
  Loader2, 
  AlertCircle, 
  CheckCircle2, 
  X,
  RefreshCw
} from 'lucide-react';

export default function ManagePlatformPage() {
  const [accounts, setAccounts] = useState<CompanyAccount[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newAccountName, setNewAccountName] = useState('');
  const [modalError, setModalError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Toggle Loading State per account ID
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const router = useRouter();

  const fetchAccounts = useCallback(async (search = '') => {
    setIsLoading(true);
    setError(null);
    try {
      const url = search.trim() ? `/accounts?search=${encodeURIComponent(search.trim())}` : '/accounts';
      const response = await api.get<CompanyAccount[]>(url);
      setAccounts(response.data);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to fetch account list.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAccounts(searchQuery);
  }, [searchQuery, fetchAccounts]);

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);

    const trimmed = newAccountName.trim();
    if (!trimmed) {
      setModalError('Account name is required.');
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await api.post<CompanyAccount>('/accounts', { name: trimmed });
      setSuccessMsg(`Account "${response.data.name}" created successfully.`);
      setNewAccountName('');
      setIsModalOpen(false);
      fetchAccounts(searchQuery);
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to create account.';
      setModalError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStatusToggle = async (account: CompanyAccount) => {
    const newStatus: AccountStatus = account.status === 'active' ? 'hidden' : 'active';
    setTogglingId(account.id);
    try {
      await api.patch(`/accounts/${account.id}/status`, { status: newStatus });
      setSuccessMsg(`Account "${account.name}" is now ${newStatus}.`);
      setAccounts(prev =>
        prev.map(a => (a.id === account.id ? { ...a, status: newStatus } : a))
      );
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to update account status.';
      setError(msg);
    } finally {
      setTogglingId(null);
    }
  };

  const formatDate = (isoString: string) => {
    if (!isoString) return 'N/A';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: '2-digit',
        year: 'numeric'
      });
    } catch {
      return isoString;
    }
  };

  return (
    <ProtectedRoute allowedRoles={['admin']}>
      <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-extrabold text-gray-900 tracking-tight flex items-center gap-2">
              <Building2 className="w-7 h-7 text-hp-navy" />
              <span>Manage Platform</span>
            </h1>
            <p className="text-xs text-gray-500 mt-1 font-medium">
              Enterprise account portfolio management & entity status control
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              setIsModalOpen(true);
              setModalError(null);
              setNewAccountName('');
            }}
            className="inline-flex items-center justify-center px-4 py-2.5 border border-transparent rounded-lg shadow-md text-sm font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-hp-navy transition duration-150"
          >
            <Plus className="w-4 h-4 mr-2 stroke-[3]" />
            <span>Create New Account</span>
          </button>
        </div>

        {/* Global Feedback Notifications */}
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

        {/* Search Bar */}
        <div className="bg-white p-4 rounded-2xl border border-gray-200 shadow-sm mb-6 flex items-center gap-3">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
              <Search className="h-4 w-4 text-gray-400" />
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search company accounts by name (e.g. Astra, Sea Limited)..."
              className="block w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-hp-navy focus:border-transparent text-xs bg-gray-50 focus:bg-white transition"
            />
          </div>
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="text-xs text-gray-500 hover:text-gray-800 font-medium px-2 py-1 rounded bg-gray-100"
            >
              Clear
            </button>
          )}
          <button
            onClick={() => fetchAccounts(searchQuery)}
            className="p-2 text-gray-500 hover:text-hp-navy rounded-lg hover:bg-gray-100 transition"
            title="Refresh Account List"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Account Table */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="p-12 flex flex-col items-center justify-center space-y-3">
              <Loader2 className="w-8 h-8 text-hp-navy animate-spin" />
              <p className="text-xs text-gray-500 font-medium">Loading target enterprise accounts...</p>
            </div>
          ) : accounts.length === 0 ? (
            <div className="p-12 text-center">
              <Building2 className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <h3 className="text-sm font-bold text-gray-800">No accounts found</h3>
              <p className="text-xs text-gray-500 mt-1">
                {searchQuery
                  ? `No account matches the query "${searchQuery}".`
                  : 'Get started by creating your first enterprise company account.'}
              </p>
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="mt-4 text-xs font-semibold text-hp-navy hover:underline"
                >
                  Clear search filter
                </button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200 text-[11px] font-bold uppercase tracking-wider text-gray-600">
                    <th className="py-3.5 px-6">Account Name</th>
                    <th className="py-3.5 px-6">Status</th>
                    <th className="py-3.5 px-6">Last Updated</th>
                    <th className="py-3.5 px-6 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 text-xs font-medium">
                  {accounts.map((account) => (
                    <tr key={account.id} className="hover:bg-slate-50/80 transition duration-150">
                      <td className="py-4 px-6 font-semibold text-gray-900">
                        <div className="flex items-center space-x-2.5">
                          <div className="w-8 h-8 rounded-lg bg-hp-navy/10 text-hp-navy flex items-center justify-center font-bold text-xs uppercase">
                            {account.name.substring(0, 2)}
                          </div>
                          <span className="text-sm text-gray-900 font-bold">{account.name}</span>
                        </div>
                      </td>

                      <td className="py-4 px-6">
                        {account.status === 'active' ? (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5"></span>
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mr-1.5"></span>
                            Hidden
                          </span>
                        )}
                      </td>

                      <td className="py-4 px-6 text-gray-500">
                        {formatDate(account.updated_at)}
                      </td>

                      <td className="py-4 px-6 text-right space-x-2">
                        <button
                          type="button"
                          onClick={() => router.push(`/admin/accounts/${account.id}`)}
                          className="inline-flex items-center space-x-1 px-3 py-1.5 bg-gray-100 hover:bg-hp-navy hover:text-white text-gray-700 rounded-lg transition text-xs font-bold"
                        >
                          <Settings2 className="w-3.5 h-3.5" />
                          <span>Manage</span>
                        </button>

                        <button
                          type="button"
                          disabled={togglingId === account.id}
                          onClick={() => handleStatusToggle(account)}
                          className={`inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                            account.status === 'active'
                              ? 'bg-amber-50 text-amber-700 hover:bg-amber-600 hover:text-white border border-amber-200'
                              : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-600 hover:text-white border border-emerald-200'
                          }`}
                        >
                          {togglingId === account.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : account.status === 'active' ? (
                            <>
                              <EyeOff className="w-3.5 h-3.5" />
                              <span>Hide</span>
                            </>
                          ) : (
                            <>
                              <Eye className="w-3.5 h-3.5" />
                              <span>Show</span>
                            </>
                          )}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

      </div>

      {/* Create Account Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden border border-gray-200">
            
            <div className="flex justify-between items-center px-6 py-4 bg-gray-50 border-b border-gray-200">
              <h3 className="text-base font-bold text-gray-900 flex items-center gap-2">
                <Building2 className="w-5 h-5 text-hp-navy" />
                <span>Create New Account</span>
              </h3>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 rounded-lg p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateAccount} className="p-6 space-y-4">
              {modalError && (
                <div className="bg-red-50 border-l-4 border-red-500 p-3 rounded-r-lg flex items-center space-x-2 text-xs font-medium text-red-700">
                  <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                  <span>{modalError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                  Account Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={newAccountName}
                  onChange={(e) => setNewAccountName(e.target.value)}
                  placeholder="e.g. Astra, Sea Limited, HP Inc"
                  className="block w-full px-3.5 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-hp-navy text-sm font-medium bg-gray-50 focus:bg-white transition"
                />
                <p className="text-[11px] text-gray-500 mt-1">
                  Unique company/entity name being analyzed. Default status will be Active.
                </p>
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
                    <span>Create Account</span>
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
