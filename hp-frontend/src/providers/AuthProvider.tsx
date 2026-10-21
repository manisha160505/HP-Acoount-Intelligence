'use client';

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { User, AuthState } from '@/types/auth';
import api from '@/services/api';
import { flushOnExit } from '@/lib/track';
import { parseApiError } from '@/lib/apiError';
import { ACTION_FAILED, NEW_PASSWORD_REFUSED } from '@/lib/uiCopy';
import {
  clearSession,
  getAccessToken,
  getSessionUser,
  onSessionChange,
  refreshSession,
  setSession,
  updateSessionUser,
  type TokenBody,
} from '@/lib/session';

interface AuthContextType extends AuthState {
  login: (email: string, pass: string) => Promise<{ success: boolean; user?: User; error?: string }>;
  logout: () => Promise<void>;
  /** Ends every session of this user; they sign in again with the new password. */
  changePassword: (current: string, next: string) => Promise<{ success: boolean; recoveryCode?: string; error?: string }>;
  /** A product tour - the dashboard's, or the admin pages' - was finished or
   *  closed: do not start it again. */
  markTourCompleted: (tour?: 'dashboard' | 'admin') => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Refusals the user must act on get this app's own wording, keyed on the
// error code; anything else is ACTION_FAILED. Never the server's text
// (client rule, approved).
function loginRefusal(err: unknown): string {
  const e = parseApiError(err);
  if (e.code === 'INVALID_CREDENTIALS' || e.status === 401) return 'Invalid email or password';
  if (e.code === 'FORBIDDEN') return 'This account has been deactivated. Contact your administrator.';
  return ACTION_FAILED;
}

function changePasswordRefusal(err: unknown): string {
  const e = parseApiError(err);
  if (e.code === 'INVALID_CREDENTIALS') return 'Your old password is not correct.';
  if (e.code === 'VALIDATION_ERROR' && e.fields?.new_password) return NEW_PASSWORD_REFUSED;
  return ACTION_FAILED;
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(getSessionUser());
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const off = onSessionChange(setUser);
    // Tokens kept there by earlier versions of this app: never read again.
    try {
      localStorage.removeItem('hp_token');
      localStorage.removeItem('hp_user');
    } catch {
      // Storage blocked; nothing to clean.
    }
    // The access token is in memory only, so a fresh page asks the server,
    // which answers from the httpOnly refresh cookie.
    refreshSession().finally(() => setIsLoading(false));
    return off;
  }, []);

  const login = async (email: string, pass: string) => {
    try {
      const response = await api.post<TokenBody>('/auth/login', { email, password: pass });
      setSession(response.data);
      return { success: true, user: response.data.user };
    } catch (err) {
      return { success: false, error: loginRefusal(err) };
    }
  };

  const logout = async () => {
    // Send queued usage events while the session that authenticates them exists.
    flushOnExit();
    try {
      await api.post('/auth/logout');
    } catch {
      // Signed out locally either way; the session lapses on its own.
    }
    clearSession();
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  };

  const changePassword = async (current: string, next: string) => {
    try {
      const res = await api.post<{ recovery_code: string }>('/auth/change-password',
        { current_password: current, new_password: next });
      // The session is already ended on the server. It is cleared here once the
      // user has seen their recovery code (see the change-password page).
      return { success: true, recoveryCode: res.data.recovery_code };
    } catch (err) {
      return { success: false, error: changePasswordRefusal(err) };
    }
  };

  const markTourCompleted = useCallback(async (tour: 'dashboard' | 'admin' = 'dashboard') => {
    const field = tour === 'admin' ? 'admin_tour_completed_at' : 'tour_completed_at';
    // Set here first so the tour does not restart before the server answers.
    updateSessionUser({ [field]: new Date().toISOString() });
    try {
      const res = await api.post<{ tour_completed_at: string }>(`/auth/me/tour-completed?tour=${tour}`);
      updateSessionUser({ [field]: res.data.tour_completed_at });
    } catch {
      // Not recorded: the tour offers itself again at the next sign-in.
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        token: getAccessToken(),
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        changePassword,
        markTourCompleted,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
