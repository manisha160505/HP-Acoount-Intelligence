'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import api from '@/services/api';
import { 
  CompanyAccount, 
  AccountDataFile, 
  DATASET_REGISTRY_LIST, 
  DatasetKey,
  DatasetRegistryItem,
  AccountInstructions,
  AccountGuardrails
} from '@/types/account';
import { 
  Building2, 
  ArrowLeft, 
  Loader2, 
  AlertCircle, 
  CheckCircle2, 
  X,
  Save,
  Database,
  FileText,
  ShieldAlert,
  UploadCloud,
  FileSpreadsheet,
  RefreshCw,
  Info,
  Check,
  Plus,
  Trash2,
  FolderOpen
} from 'lucide-react';

type TabType = 'details' | 'data' | 'instructions' | 'guardrails';

export default function ManageAccountPage() {
  const params = useParams();
  const accountId = params.id as string;
  const router = useRouter();

  const [account, setAccount] = useState<CompanyAccount | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('details');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Account Details Form State
  const [accountName, setAccountName] = useState('');
  const [isSavingDetails, setIsSavingDetails] = useState(false);
  const [saveDetailsSuccess, setSaveDetailsSuccess] = useState<string | null>(null);
  const [saveDetailsError, setSaveDetailsError] = useState<string | null>(null);

  // Data Management State
  const [dataFiles, setDataFiles] = useState<AccountDataFile[]>([]);
  const [isLoadingData, setIsLoadingData] = useState(false);
  const [selectedDatasetKey, setSelectedCategoryKey] = useState<DatasetKey>('firmographics');
  const [fileToReplaceId, setFileToReplaceId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deletingFileId, setDeletingFileId] = useState<string | null>(null);
  const [uploadedFileModal, setUploadedFileModal] = useState<AccountDataFile | null>(null);

  // Instructions State
  const [instructionsText, setInstructionsText] = useState('');
  const [isLoadingInstructions, setIsLoadingInstructions] = useState(false);
  const [isSavingInstructions, setIsSavingInstructions] = useState(false);
  const [instructionsSuccess, setInstructionsSuccess] = useState<string | null>(null);
  const [instructionsError, setInstructionsError] = useState<string | null>(null);

  // Guardrails State
  const [guardrailsEnabled, setGuardrailsEnabled] = useState(false);
  const [guardrailsText, setGuardrailsText] = useState('');
  const [isLoadingGuardrails, setIsLoadingGuardrails] = useState(false);
  const [isSavingGuardrails, setIsSavingGuardrails] = useState(false);
  const [guardrailsSuccess, setGuardrailsSuccess] = useState<string | null>(null);
  const [guardrailsError, setGuardrailsError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadCardRef = useRef<HTMLDivElement>(null);

  const fetchAccountDetails = useCallback(async () => {
    if (!accountId) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.get<CompanyAccount>(`/accounts/${accountId}`);
      setAccount(response.data);
      setAccountName(response.data.name);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to load account details.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [accountId]);

  const fetchAccountDataFiles = useCallback(async () => {
    if (!accountId) return;
    setIsLoadingData(true);
    try {
      const response = await api.get<AccountDataFile[]>(`/accounts/${accountId}/data`);
      setDataFiles(response.data);
    } catch (err: any) {
      // Non-blocking
    } finally {
      setIsLoadingData(false);
    }
  }, [accountId]);

  const fetchInstructions = useCallback(async () => {
    if (!accountId) return;
    setIsLoadingInstructions(true);
    setInstructionsError(null);
    try {
      const response = await api.get<AccountInstructions>(`/accounts/${accountId}/instructions`);
      setInstructionsText(response.data.instructions_text || '');
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to load instructions.';
      setInstructionsError(msg);
    } finally {
      setIsLoadingInstructions(false);
    }
  }, [accountId]);

  const fetchGuardrails = useCallback(async () => {
    if (!accountId) return;
    setIsLoadingGuardrails(true);
    setGuardrailsError(null);
    try {
      const response = await api.get<AccountGuardrails>(`/accounts/${accountId}/guardrails`);
      setGuardrailsEnabled(response.data.enabled || false);
      setGuardrailsText(response.data.guardrails_text || '');
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to load guardrails.';
      setGuardrailsError(msg);
    } finally {
      setIsLoadingGuardrails(false);
    }
  }, [accountId]);

  useEffect(() => {
    fetchAccountDetails();
    fetchAccountDataFiles();
  }, [fetchAccountDetails, fetchAccountDataFiles]);

  useEffect(() => {
    if (activeTab === 'instructions') {
      fetchInstructions();
    } else if (activeTab === 'guardrails') {
      fetchGuardrails();
    }
  }, [activeTab, fetchInstructions, fetchGuardrails]);

  const handleSaveDetails = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveDetailsError(null);
    setSaveDetailsSuccess(null);

    const trimmed = accountName.trim();
    if (!trimmed) {
      setSaveDetailsError('Account name cannot be empty.');
      return;
    }

    setIsSavingDetails(true);
    try {
      const response = await api.patch<CompanyAccount>(`/accounts/${accountId}`, {
        name: trimmed
      });
      setAccount(response.data);
      setAccountName(response.data.name);
      setSaveDetailsSuccess(`Account name successfully updated to "${response.data.name}".`);
      setTimeout(() => setSaveDetailsSuccess(null), 4000);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to update account name.';
      setSaveDetailsError(msg);
    } finally {
      setIsSavingDetails(false);
    }
  };

  const handleSaveInstructions = async (e: React.FormEvent) => {
    e.preventDefault();
    setInstructionsError(null);
    setInstructionsSuccess(null);

    setIsSavingInstructions(true);
    try {
      const response = await api.put<AccountInstructions>(`/accounts/${accountId}/instructions`, {
        instructions_text: instructionsText
      });
      setInstructionsText(response.data.instructions_text || '');
      setInstructionsSuccess('Account-specific instructions saved successfully.');
      setTimeout(() => setInstructionsSuccess(null), 4000);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to save instructions.';
      setInstructionsError(msg);
    } finally {
      setIsSavingInstructions(false);
    }
  };

  const handleSaveGuardrails = async (e: React.FormEvent) => {
    e.preventDefault();
    setGuardrailsError(null);
    setGuardrailsSuccess(null);

    setIsSavingGuardrails(true);
    try {
      const response = await api.put<AccountGuardrails>(`/accounts/${accountId}/guardrails`, {
        enabled: guardrailsEnabled,
        guardrails_text: guardrailsText
      });
      setGuardrailsEnabled(response.data.enabled);
      setGuardrailsText(response.data.guardrails_text || '');
      setGuardrailsSuccess('Account-specific guardrails saved successfully.');
      setTimeout(() => setGuardrailsSuccess(null), 4000);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to save guardrails.';
      setGuardrailsError(msg);
    } finally {
      setIsSavingGuardrails(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setUploadError(null);
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      const registryItem = DATASET_REGISTRY_LIST.find(d => d.key === selectedDatasetKey);
      const allowedExts = registryItem?.allowed_extensions || ['.csv'];

      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!allowedExts.includes(ext)) {
        setUploadError(`Unsupported format '${ext}'. Allowed formats for ${registryItem?.display_name}: ${allowedExts.join(', ')}`);
        setSelectedFile(null);
        return;
      }
      if (file.size === 0) {
        setUploadError('The selected file is empty (0 bytes). Please upload a valid data file.');
        setSelectedFile(null);
        return;
      }
      setSelectedFile(file);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setUploadError(null);
    setUploadSuccess(null);

    if (!selectedFile) {
      setUploadError('Please select a file to upload.');
      return;
    }

    const formData = new FormData();
    formData.append('dataset_key', selectedDatasetKey);
    formData.append('file', selectedFile);
    if (fileToReplaceId) {
      formData.append('file_id_to_replace', fileToReplaceId);
    }

    setIsUploading(true);
    try {
      const response = await api.post<AccountDataFile>(`/accounts/${accountId}/data`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      const registryItem = DATASET_REGISTRY_LIST.find(c => c.key === selectedDatasetKey);
      setUploadSuccess(`Uploaded dataset for "${registryItem?.display_name}" (${response.data.original_filename}). Stored as "${response.data.stored_filename}".`);
      setUploadedFileModal(response.data);
      
      setSelectedFile(null);
      setFileToReplaceId(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }

      fetchAccountDataFiles();
      setTimeout(() => setUploadSuccess(null), 4000);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to upload dataset.';
      setUploadError(msg);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteFile = async (fileId: string, filename: string) => {
    if (!window.confirm(`Are you sure you want to delete the file "${filename}"?`)) {
      return;
    }

    setDeletingFileId(fileId);
    setUploadError(null);
    try {
      await api.delete(`/accounts/${accountId}/data/${fileId}`);
      setUploadSuccess(`Deleted file "${filename}".`);
      fetchAccountDataFiles();
      setTimeout(() => setUploadSuccess(null), 3000);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to delete file.';
      setUploadError(msg);
    } finally {
      setDeletingFileId(null);
    }
  };

  const openUploadForDataset = (item: DatasetRegistryItem, replaceFileId: string | null = null) => {
    setSelectedCategoryKey(item.key);
    setFileToReplaceId(replaceFileId);
    setSelectedFile(null);
    setUploadError(null);
    setUploadSuccess(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    if (uploadCardRef.current) {
      uploadCardRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const formatFileSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatDate = (isoString: string) => {
    if (!isoString) return 'N/A';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return isoString;
    }
  };

  // Group datasets by category group
  const groupedDatasets = DATASET_REGISTRY_LIST.reduce((acc, item) => {
    if (!acc[item.group]) {
      acc[item.group] = [];
    }
    acc[item.group].push(item);
    return acc;
  }, {} as Record<string, DatasetRegistryItem[]>);

  const selectedRegistryItem = DATASET_REGISTRY_LIST.find(d => d.key === selectedDatasetKey) || DATASET_REGISTRY_LIST[0];

  return (
    <ProtectedRoute allowedRoles={['admin']}>
      <div className="max-w-6xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        
        {/* Navigation Bar */}
        <button
          type="button"
          onClick={() => router.push('/admin/platform')}
          className="inline-flex items-center space-x-2 text-xs font-bold text-gray-600 hover:text-hp-navy mb-6 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Manage Platform</span>
        </button>

        {isLoading ? (
          <div className="bg-white rounded-2xl p-12 border border-gray-200 shadow-sm flex flex-col items-center justify-center space-y-3">
            <Loader2 className="w-8 h-8 text-hp-navy animate-spin" />
            <p className="text-xs text-gray-500 font-medium">Loading account workspace...</p>
          </div>
        ) : error ? (
          <div className="bg-white rounded-2xl p-8 border border-red-200 shadow-sm">
            <div className="flex items-center space-x-3 text-red-600 mb-2">
              <AlertCircle className="w-6 h-6" />
              <h3 className="font-bold text-sm">Error Loading Account</h3>
            </div>
            <p className="text-xs text-gray-600 mb-4">{error}</p>
            <button
              onClick={() => router.push('/admin/platform')}
              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-xs font-bold text-gray-800 rounded-lg transition"
            >
              Return to Platform Directory
            </button>
          </div>
        ) : account ? (
          <div className="space-y-6">
            
            {/* Account Title Banner */}
            <div className="bg-white rounded-2xl p-8 border border-gray-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 rounded-xl bg-hp-navy/10 text-hp-navy flex items-center justify-center font-extrabold text-lg uppercase">
                  {account.name.substring(0, 2)}
                </div>
                <div>
                  <div className="flex items-center space-x-3">
                    <h1 className="text-2xl font-extrabold text-gray-900 tracking-tight">
                      {account.name}
                    </h1>
                    {account.status === 'active' ? (
                      <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                        Active
                      </span>
                    ) : (
                      <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                        Hidden
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-mono text-gray-400 mt-1">
                    Account ID: {account.id}
                  </p>
                </div>
              </div>

              <div className="bg-gray-50 px-4 py-2.5 rounded-xl border border-gray-200 text-right text-xs space-y-0.5">
                <p className="text-gray-500 font-medium">
                  Created: <span className="text-gray-800 font-bold">{formatDate(account.created_at)}</span>
                </p>
                <p className="text-gray-500 font-medium">
                  Updated: <span className="text-gray-800 font-bold">{formatDate(account.updated_at)}</span>
                </p>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="flex border-b border-gray-200 bg-gray-50/50">
                <button
                  type="button"
                  onClick={() => setActiveTab('details')}
                  className={`flex-1 flex items-center justify-center space-x-2 py-3.5 px-4 text-xs font-bold border-b-2 transition ${
                    activeTab === 'details'
                      ? 'border-hp-navy text-hp-navy bg-white'
                      : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
                  }`}
                >
                  <Building2 className="w-4 h-4" />
                  <span>Account Details</span>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveTab('data')}
                  className={`flex-1 flex items-center justify-center space-x-2 py-3.5 px-4 text-xs font-bold border-b-2 transition ${
                    activeTab === 'data'
                      ? 'border-hp-navy text-hp-navy bg-white'
                      : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
                  }`}
                >
                  <Database className="w-4 h-4" />
                  <span>Data ({dataFiles.filter(f => f.status === 'active').length} Active Files)</span>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveTab('instructions')}
                  className={`flex-1 flex items-center justify-center space-x-2 py-3.5 px-4 text-xs font-bold border-b-2 transition ${
                    activeTab === 'instructions'
                      ? 'border-hp-navy text-hp-navy bg-white'
                      : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
                  }`}
                >
                  <FileText className="w-4 h-4" />
                  <span>Instructions</span>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveTab('guardrails')}
                  className={`flex-1 flex items-center justify-center space-x-2 py-3.5 px-4 text-xs font-bold border-b-2 transition ${
                    activeTab === 'guardrails'
                      ? 'border-hp-navy text-hp-navy bg-white'
                      : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
                  }`}
                >
                  <ShieldAlert className="w-4 h-4" />
                  <span>Guardrails</span>
                </button>
              </div>

              {/* Tab Content Container */}
              <div className="p-8">
                
                {/* Tab 1: Account Details Form */}
                {activeTab === 'details' && (
                  <div className="max-w-2xl">
                    <div className="mb-6">
                      <h2 className="text-base font-bold text-gray-900">General Account Configuration</h2>
                      <p className="text-xs text-gray-500 mt-1">
                        Update the target company entity name. Changes will update platform records immediately.
                      </p>
                    </div>

                    {saveDetailsSuccess && (
                      <div className="mb-6 bg-emerald-50 border-l-4 border-emerald-500 p-4 rounded-r-lg flex items-center justify-between text-emerald-800 text-xs font-semibold shadow-sm">
                        <div className="flex items-center space-x-2">
                          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                          <span>{saveDetailsSuccess}</span>
                        </div>
                        <button onClick={() => setSaveDetailsSuccess(null)}>
                          <X className="w-4 h-4 text-emerald-600" />
                        </button>
                      </div>
                    )}

                    {saveDetailsError && (
                      <div className="mb-6 bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg flex items-center justify-between text-red-800 text-xs font-semibold shadow-sm">
                        <div className="flex items-center space-x-2">
                          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                          <span>{saveDetailsError}</span>
                        </div>
                        <button onClick={() => setSaveDetailsError(null)}>
                          <X className="w-4 h-4 text-red-600" />
                        </button>
                      </div>
                    )}

                    <form onSubmit={handleSaveDetails} className="space-y-6">
                      <div>
                        <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">
                          Account Name <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          required
                          value={accountName}
                          onChange={(e) => setAccountName(e.target.value)}
                          placeholder="Company name..."
                          className="block w-full px-3.5 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-hp-navy text-sm font-medium bg-white shadow-sm transition"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">
                          Account ID (System Read-Only)
                        </label>
                        <input
                          type="text"
                          disabled
                          value={account.id}
                          className="block w-full px-3.5 py-2.5 border border-gray-200 rounded-lg text-sm font-mono bg-gray-100 text-gray-600 cursor-not-allowed"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">
                          Visibility Status (System Read-Only)
                        </label>
                        <div className="flex items-center space-x-3 p-3 border border-gray-200 rounded-lg bg-gray-100 text-sm font-medium">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${
                            account.status === 'active' 
                              ? 'bg-emerald-100 text-emerald-800 border border-emerald-200' 
                              : 'bg-amber-100 text-amber-800 border border-amber-200'
                          }`}>
                            {account.status === 'active' ? 'Active' : 'Hidden'}
                          </span>
                          <span className="text-xs text-gray-500">
                            (Status toggle controlled from Manage Platform table)
                          </span>
                        </div>
                      </div>

                      <div className="pt-4 border-t border-gray-100 flex items-center justify-between">
                        <button
                          type="submit"
                          disabled={isSavingDetails}
                          className="inline-flex items-center space-x-2 px-5 py-2.5 border border-transparent rounded-lg shadow-md text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none transition disabled:opacity-50"
                        >
                          {isSavingDetails ? (
                            <>
                              <Loader2 className="w-4 h-4 animate-spin" />
                              <span>Saving Changes...</span>
                            </>
                          ) : (
                            <>
                              <Save className="w-4 h-4" />
                              <span>Save Changes</span>
                            </>
                          )}
                        </button>
                      </div>
                    </form>
                  </div>
                )}

                {/* Tab 2: 23 Client-Defined Data Categories Management */}
                {activeTab === 'data' && (
                  <div className="space-y-8">
                    
                    {/* Header Banner */}
                    <div className="bg-slate-900 text-white p-6 rounded-2xl border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div>
                        <h2 className="text-lg font-bold flex items-center gap-2 text-white">
                          <Database className="w-5 h-5 text-hp-accent" />
                          <span>Raw Data Management — {account.name}</span>
                        </h2>
                        <p className="text-xs text-gray-300 mt-1">
                          23 Client-Defined Datasets. Single-file datasets persist canonically. News datasets support multi-file coexistence.
                        </p>
                      </div>

                      <button
                        onClick={fetchAccountDataFiles}
                        className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-gray-200 text-xs font-bold rounded-lg border border-slate-700 transition"
                        title="Refresh Stored Datasets"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isLoadingData ? 'animate-spin' : ''}`} />
                        <span>Refresh Datasets</span>
                      </button>
                    </div>

                    {/* Feedback Messages */}
                    {uploadSuccess && (
                      <div className="bg-emerald-50 border-l-4 border-emerald-500 p-4 rounded-r-lg flex items-center justify-between text-emerald-800 text-xs font-semibold shadow-sm">
                        <div className="flex items-center space-x-2">
                          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                          <span>{uploadSuccess}</span>
                        </div>
                        <button onClick={() => setUploadSuccess(null)}>
                          <X className="w-4 h-4 text-emerald-600" />
                        </button>
                      </div>
                    )}

                    {uploadError && (
                      <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg flex items-center justify-between text-red-800 text-xs font-semibold shadow-sm">
                        <div className="flex items-center space-x-2">
                          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                          <span>{uploadError}</span>
                        </div>
                        <button onClick={() => setUploadError(null)}>
                          <X className="w-4 h-4 text-red-600" />
                        </button>
                      </div>
                    )}

                    {/* Upload / Replace Form Card */}
                    <div ref={uploadCardRef} className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
                      <div className="flex items-center justify-between mb-4 pb-3 border-b border-gray-100">
                        <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                          <UploadCloud className="w-4 h-4 text-hp-navy" />
                          <span>
                            {fileToReplaceId ? `Replace Specific File` : `Upload Dataset File`} —{' '}
                            <span className="text-hp-navy">{selectedRegistryItem.display_name}</span>
                          </span>
                        </h3>
                        {fileToReplaceId && (
                          <button
                            onClick={() => setFileToReplaceId(null)}
                            className="text-xs text-gray-500 hover:text-gray-800 underline font-medium"
                          >
                            Cancel File Replacement
                          </button>
                        )}
                      </div>

                      <form onSubmit={handleUploadSubmit} className="space-y-5">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                          
                          {/* Dataset Selector */}
                          <div>
                            <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">
                              Target Dataset <span className="text-red-500">*</span>
                            </label>
                            <select
                              value={selectedDatasetKey}
                              onChange={(e) => {
                                setSelectedCategoryKey(e.target.value as DatasetKey);
                                setFileToReplaceId(null);
                                setSelectedFile(null);
                              }}
                              className="block w-full px-3.5 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-hp-navy text-xs font-medium bg-white shadow-sm transition"
                            >
                              {DATASET_REGISTRY_LIST.map((ds) => (
                                <option key={ds.key} value={ds.key}>
                                  {ds.display_name} ({ds.key}) [{ds.type === 'multi_file' ? 'Multi-File' : 'Single-File CSV'}]
                                </option>
                              ))}
                            </select>
                            <p className="text-[11px] text-gray-500 mt-1">
                              {selectedRegistryItem.description}
                            </p>
                          </div>

                          {/* File Input */}
                          <div>
                            <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">
                              Data File <span className="text-red-500">*</span>
                            </label>
                            <input
                              ref={fileInputRef}
                              type="file"
                              accept={selectedRegistryItem.allowed_extensions.join(',')}
                              onChange={handleFileChange}
                              className="block w-full text-xs text-gray-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-hp-navy file:text-white hover:file:bg-hp-blue cursor-pointer bg-white border border-gray-300 rounded-lg p-1"
                            />
                            <p className="text-[11px] text-gray-500 mt-1">
                              Allowed extensions: <strong className="text-gray-700">{selectedRegistryItem.allowed_extensions.join(', ')}</strong>.
                              {selectedRegistryItem.type === 'single_file_csv' ? (
                                <span> Stored canonically as <code className="text-hp-navy font-mono">{selectedRegistryItem.canonical_filename}</code>.</span>
                              ) : (
                                <span> Multiple files co-exist under this dataset.</span>
                              )}
                            </p>
                          </div>

                        </div>

                        {/* Selected File Notice */}
                        {selectedFile && (
                          <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 flex items-center justify-between text-xs text-blue-900 font-medium">
                            <div className="flex items-center space-x-2">
                              <FileSpreadsheet className="w-4 h-4 text-hp-blue" />
                              <span>
                                Ready to upload for <strong className="font-bold">{selectedRegistryItem.display_name}</strong>:{' '}
                                <strong className="font-mono text-hp-navy">{selectedFile.name}</strong> ({formatFileSize(selectedFile.size)})
                              </span>
                            </div>
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedFile(null);
                                if (fileInputRef.current) fileInputRef.current.value = '';
                              }}
                              className="text-blue-700 hover:text-blue-900"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        )}

                        <div className="flex justify-end pt-2">
                          <button
                            type="submit"
                            disabled={isUploading || !selectedFile}
                            className="inline-flex items-center space-x-2 px-5 py-2.5 border border-transparent rounded-lg shadow-md text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none transition disabled:opacity-50"
                          >
                            {isUploading ? (
                              <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                <span>Uploading Dataset...</span>
                              </>
                            ) : (
                              <>
                                <UploadCloud className="w-4 h-4" />
                                <span>{fileToReplaceId ? 'Replace Selected File' : selectedRegistryItem.type === 'multi_file' ? 'Add File to Dataset' : 'Upload / Replace Dataset'}</span>
                              </>
                            )}
                          </button>
                        </div>
                      </form>
                    </div>

                    {/* 23 Client-Defined Datasets Directory Grid */}
                    <div className="space-y-6">
                      {Object.entries(groupedDatasets).map(([groupName, items]) => (
                        <div key={groupName} className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
                          
                          <div className="px-6 py-3.5 bg-gray-50/80 border-b border-gray-200 flex items-center justify-between">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-800 flex items-center gap-2">
                              <FolderOpen className="w-4 h-4 text-hp-navy" />
                              <span>{groupName}</span>
                              <span className="text-gray-400 text-[10px]">({items.length} Datasets)</span>
                            </h3>
                          </div>

                          <div className="divide-y divide-gray-100">
                            {items.map((item) => {
                              const activeFiles = dataFiles.filter(
                                f => (f.dataset_key === item.key || f.category === item.key) && f.status === 'active'
                              );

                              return (
                                <div key={item.key} className="p-5 hover:bg-slate-50/50 transition">
                                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-2">
                                    <div>
                                      <div className="flex items-center space-x-2.5">
                                        <h4 className="text-sm font-bold text-gray-900">{item.display_name}</h4>
                                        <code className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded font-mono">
                                          {item.key}
                                        </code>
                                        {item.type === 'multi_file' ? (
                                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 border border-purple-200">
                                            Multi-File
                                          </span>
                                        ) : (
                                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-hp-blue border border-blue-200">
                                            Single-File CSV
                                          </span>
                                        )}
                                      </div>
                                      <p className="text-xs text-gray-500 mt-0.5">{item.description}</p>
                                    </div>

                                    {/* Primary Action Button */}
                                    <div className="flex items-center space-x-2">
                                      {item.type === 'single_file_csv' ? (
                                        activeFiles.length > 0 ? (
                                          <button
                                            type="button"
                                            onClick={() => openUploadForDataset(item)}
                                            className="px-3.5 py-1.5 bg-hp-navy/10 hover:bg-hp-navy hover:text-white text-hp-navy rounded-lg text-xs font-bold transition flex items-center space-x-1"
                                          >
                                            <RefreshCw className="w-3.5 h-3.5 mr-1" />
                                            <span>Replace</span>
                                          </button>
                                        ) : (
                                          <button
                                            type="button"
                                            onClick={() => openUploadForDataset(item)}
                                            className="px-3.5 py-1.5 bg-gray-100 hover:bg-hp-navy hover:text-white text-gray-700 rounded-lg text-xs font-bold transition flex items-center space-x-1"
                                          >
                                            <Plus className="w-3.5 h-3.5 mr-1" />
                                            <span>Upload</span>
                                          </button>
                                        )
                                      ) : (
                                        <button
                                          type="button"
                                          onClick={() => openUploadForDataset(item)}
                                          className="px-3.5 py-1.5 bg-purple-50 hover:bg-purple-600 hover:text-white text-purple-700 border border-purple-200 rounded-lg text-xs font-bold transition flex items-center space-x-1"
                                        >
                                          <Plus className="w-3.5 h-3.5 mr-1" />
                                          <span>Add File</span>
                                        </button>
                                      )}
                                    </div>
                                  </div>

                                  {/* Dataset Storage Status View */}
                                  {activeFiles.length === 0 ? (
                                    <div className="mt-2 text-xs text-gray-400 italic flex items-center space-x-1.5 bg-gray-50/80 p-2.5 rounded-lg border border-dashed border-gray-200">
                                      <Info className="w-3.5 h-3.5 text-gray-400" />
                                      <span>Not uploaded</span>
                                    </div>
                                  ) : (
                                    <div className="mt-3 space-y-2">
                                      {activeFiles.map((file) => (
                                        <div 
                                          key={file.id} 
                                          className="bg-gray-50 p-3 rounded-xl border border-gray-200 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs"
                                        >
                                          <div className="flex items-center space-x-3">
                                            <FileSpreadsheet className="w-4 h-4 text-hp-navy flex-shrink-0" />
                                            <div>
                                              <div className="flex items-center space-x-2">
                                                <span className="font-bold text-gray-800 font-mono">{file.original_filename}</span>
                                                <span className="text-[10px] text-gray-400 font-mono">
                                                  (stored as: <code className="text-hp-navy">{file.stored_filename}</code>)
                                                </span>
                                              </div>
                                              <p className="text-[11px] text-gray-500 mt-0.5">
                                                {file.row_count} rows • {formatFileSize(file.file_size)} • Uploaded: {formatDate(file.uploaded_at)}
                                              </p>
                                            </div>
                                          </div>

                                          <div className="flex items-center space-x-2 justify-end">
                                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                                              <Check className="w-3 h-3 mr-1 text-emerald-600" />
                                              Active
                                            </span>

                                            {item.type === 'multi_file' && (
                                              <>
                                                <button
                                                  type="button"
                                                  onClick={() => openUploadForDataset(item, file.id)}
                                                  className="px-2.5 py-1 bg-gray-200 hover:bg-hp-navy hover:text-white text-gray-700 rounded text-[11px] font-bold transition"
                                                >
                                                  Replace
                                                </button>
                                                <button
                                                  type="button"
                                                  disabled={deletingFileId === file.id}
                                                  onClick={() => handleDeleteFile(file.id, file.original_filename)}
                                                  className="p-1 bg-red-50 hover:bg-red-600 text-red-600 hover:text-white border border-red-200 rounded transition"
                                                  title="Delete this file"
                                                >
                                                  {deletingFileId === file.id ? (
                                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                  ) : (
                                                    <Trash2 className="w-3.5 h-3.5" />
                                                  )}
                                                </button>
                                              </>
                                            )}
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}

                                </div>
                              );
                            })}
                          </div>

                        </div>
                      ))}
                    </div>

                  </div>
                )}

                {/* Tab 3: Account-Specific Instructions */}
                {activeTab === 'instructions' && (
                  <div className="max-w-3xl space-y-6">
                    <div>
                      <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
                        <FileText className="w-5 h-5 text-hp-navy" />
                        <span>Account-Specific Instructions</span>
                      </h2>
                      <p className="text-xs text-gray-500 mt-1">
                        Configure custom guidelines, focus topics, or special regional instructions for this specific company account (<strong className="text-gray-800">{account.name}</strong>).
                      </p>
                    </div>

                    {instructionsSuccess && (
                      <div className="bg-emerald-50 border-l-4 border-emerald-500 p-4 rounded-r-lg flex items-center justify-between text-emerald-800 text-xs font-semibold shadow-sm">
                        <div className="flex items-center space-x-2">
                          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                          <span>{instructionsSuccess}</span>
                        </div>
                        <button onClick={() => setInstructionsSuccess(null)}>
                          <X className="w-4 h-4 text-emerald-600" />
                        </button>
                      </div>
                    )}

                    {instructionsError && (
                      <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg flex items-center justify-between text-red-800 text-xs font-semibold shadow-sm">
                        <div className="flex items-center space-x-2">
                          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                          <span>{instructionsError}</span>
                        </div>
                        <button onClick={() => setInstructionsError(null)}>
                          <X className="w-4 h-4 text-red-600" />
                        </button>
                      </div>
                    )}

                    {isLoadingInstructions ? (
                      <div className="p-12 text-center flex flex-col items-center justify-center space-y-2">
                        <Loader2 className="w-6 h-6 text-hp-navy animate-spin" />
                        <p className="text-xs text-gray-500">Loading stored account instructions...</p>
                      </div>
                    ) : (
                      <form onSubmit={handleSaveInstructions} className="space-y-4">
                        <div>
                          <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">
                            Instructions Text
                          </label>
                          <textarea
                            rows={8}
                            value={instructionsText}
                            onChange={(e) => setInstructionsText(e.target.value)}
                            placeholder="Enter account-specific instructions (e.g. Focus analysis on enterprise AI infrastructure, cloud migrations in SEA region, and PC refresh cycles)..."
                            className="block w-full p-4 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-hp-navy text-xs font-mono leading-relaxed bg-white shadow-sm transition"
                          />
                          <p className="text-[11px] text-gray-500 mt-2">
                            These instructions will append to standard system prompts during processing runtime for this specific account.
                          </p>
                        </div>

                        <div className="flex items-center justify-between pt-2">
                          {instructionsText && (
                            <button
                              type="button"
                              onClick={() => setInstructionsText('')}
                              className="text-xs text-gray-500 hover:text-red-600 font-medium underline"
                            >
                              Clear Text
                            </button>
                          )}
                          <div className="ml-auto">
                            <button
                              type="submit"
                              disabled={isSavingInstructions}
                              className="inline-flex items-center space-x-2 px-5 py-2.5 border border-transparent rounded-lg shadow-md text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none transition disabled:opacity-50"
                            >
                              {isSavingInstructions ? (
                                <>
                                  <Loader2 className="w-4 h-4 animate-spin" />
                                  <span>Saving Instructions...</span>
                                </>
                              ) : (
                                <>
                                  <Save className="w-4 h-4" />
                                  <span>Save Instructions</span>
                                </>
                              )}
                            </button>
                          </div>
                        </div>
                      </form>
                    )}
                  </div>
                )}

                {/* Tab 4: Account-Specific Guardrails */}
                {activeTab === 'guardrails' && (
                  <div className="max-w-3xl space-y-6">
                    <div>
                      <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
                        <ShieldAlert className="w-5 h-5 text-hp-navy" />
                        <span>Account-Specific Guardrails</span>
                      </h2>
                      <p className="text-xs text-gray-500 mt-1">
                        Configure linguistic guardrails, threshold overrides, or restricted claim rules for this specific company account (<strong className="text-gray-800">{account.name}</strong>).
                      </p>
                    </div>

                    {guardrailsSuccess && (
                      <div className="bg-emerald-50 border-l-4 border-emerald-500 p-4 rounded-r-lg flex items-center justify-between text-emerald-800 text-xs font-semibold shadow-sm">
                        <div className="flex items-center space-x-2">
                          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                          <span>{guardrailsSuccess}</span>
                        </div>
                        <button onClick={() => setGuardrailsSuccess(null)}>
                          <X className="w-4 h-4 text-emerald-600" />
                        </button>
                      </div>
                    )}

                    {guardrailsError && (
                      <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg flex items-center justify-between text-red-800 text-xs font-semibold shadow-sm">
                        <div className="flex items-center space-x-2">
                          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                          <span>{guardrailsError}</span>
                        </div>
                        <button onClick={() => setGuardrailsError(null)}>
                          <X className="w-4 h-4 text-red-600" />
                        </button>
                      </div>
                    )}

                    {isLoadingGuardrails ? (
                      <div className="p-12 text-center flex flex-col items-center justify-center space-y-2">
                        <Loader2 className="w-6 h-6 text-hp-navy animate-spin" />
                        <p className="text-xs text-gray-500">Loading stored account guardrails...</p>
                      </div>
                    ) : (
                      <form onSubmit={handleSaveGuardrails} className="space-y-6">
                        
                        {/* Toggle Switch */}
                        <div className="bg-gray-50 p-4 rounded-xl border border-gray-200 flex items-center justify-between">
                          <div>
                            <span className="text-xs font-bold text-gray-900 block">
                              Enable Account Guardrails
                            </span>
                            <span className="text-[11px] text-gray-500">
                              When enabled, account-specific guardrail content will be enforced alongside standard platform guardrails.
                            </span>
                          </div>

                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={guardrailsEnabled}
                              onChange={(e) => setGuardrailsEnabled(e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-gray-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-hp-navy"></div>
                          </label>
                        </div>

                        {/* Textarea Editor */}
                        <div>
                          <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">
                            Guardrail Content & Rules
                          </label>
                          <textarea
                            rows={8}
                            value={guardrailsText}
                            onChange={(e) => setGuardrailsText(e.target.value)}
                            placeholder="Enter account-specific guardrails (e.g. Do not use unsupported superlatives such as 'market leader' or 'guaranteed opportunity'. Override confidence threshold to 50%)..."
                            className="block w-full p-4 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-hp-navy text-xs font-mono leading-relaxed bg-white shadow-sm transition"
                          />
                          <p className="text-[11px] text-gray-500 mt-2">
                            Specify restricted terms, confidence score overrides, or defensible language requirements for this account.
                          </p>
                        </div>

                        <div className="flex items-center justify-between pt-2">
                          {guardrailsText && (
                            <button
                              type="button"
                              onClick={() => setGuardrailsText('')}
                              className="text-xs text-gray-500 hover:text-red-600 font-medium underline"
                            >
                              Clear Text
                            </button>
                          )}
                          <div className="ml-auto">
                            <button
                              type="submit"
                              disabled={isSavingGuardrails}
                              className="inline-flex items-center space-x-2 px-5 py-2.5 border border-transparent rounded-lg shadow-md text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none transition disabled:opacity-50"
                            >
                              {isSavingGuardrails ? (
                                <>
                                  <Loader2 className="w-4 h-4 animate-spin" />
                                  <span>Saving Guardrails...</span>
                                </>
                              ) : (
                                <>
                                  <Save className="w-4 h-4" />
                                  <span>Save Guardrails</span>
                                </>
                              )}
                            </button>
                          </div>
                        </div>
                      </form>
                    )}
                  </div>
                )}

              </div>
            </div>

          </div>
        ) : null}

      </div>

      {/* Upload Success Confirmation Pop-Up Modal */}
      {uploadedFileModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full overflow-hidden border border-gray-200">
            
            <div className="flex justify-between items-center px-6 py-4 bg-emerald-50 border-b border-emerald-100">
              <h3 className="text-sm font-bold text-emerald-900 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                <span>Dataset File Uploaded Successfully</span>
              </h3>
              <button
                type="button"
                onClick={() => setUploadedFileModal(null)}
                className="text-gray-400 hover:text-gray-600 rounded-lg p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-4 text-xs font-medium">
              <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                <div className="flex justify-between border-b border-slate-200 pb-1.5">
                  <span className="text-gray-500 font-bold uppercase text-[10px]">Dataset Category:</span>
                  <span className="font-bold text-hp-navy capitalize">{uploadedFileModal.display_name || uploadedFileModal.dataset_key}</span>
                </div>

                <div className="flex justify-between border-b border-slate-200 pb-1.5">
                  <span className="text-gray-500 font-bold uppercase text-[10px]">Original Filename:</span>
                  <span className="font-mono text-gray-800">{uploadedFileModal.original_filename}</span>
                </div>

                <div className="flex justify-between border-b border-slate-200 pb-1.5">
                  <span className="text-gray-500 font-bold uppercase text-[10px]">Stored Canonical Filename:</span>
                  <span className="font-mono text-emerald-700 font-bold">{uploadedFileModal.stored_filename}</span>
                </div>

                <div className="flex justify-between border-b border-slate-200 pb-1.5">
                  <span className="text-gray-500 font-bold uppercase text-[10px]">Parsed Rows / Size:</span>
                  <span className="text-gray-800 font-semibold">{uploadedFileModal.row_count} rows ({formatFileSize(uploadedFileModal.file_size)})</span>
                </div>

                <div className="pt-1">
                  <span className="text-gray-500 font-bold uppercase text-[10px] block mb-1">Server Storage Location:</span>
                  <code className="bg-slate-200/80 px-2 py-1 rounded text-[10px] font-mono text-slate-800 block break-all">
                    {uploadedFileModal.file_path}
                  </code>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setUploadedFileModal(null)}
                  className="px-5 py-2.5 bg-hp-navy hover:bg-hp-blue text-white rounded-lg text-xs font-bold shadow-md transition"
                >
                  Done / Dismiss
                </button>
              </div>
            </div>

          </div>
        </div>
      )}
    </ProtectedRoute>
  );
}
