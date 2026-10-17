'use client';

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { User, AuthState } from '@/types/auth';
import api from '@/services/api';
import { flushOnExit } from '@/lib/track';
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
  changePassword: (current: string, next: string) => Promise<{ success: boolean; error?: string }>;
  /** The product tour was finished or closed: do not start it again. */
  markTourCompleted: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function errorMessage(err: any, fallback: string): string {
  return err?.response?.data?.error?.message || err?.response?.data?.detail || fallback;
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
    } catch (err: any) {
      return { success: false, error: errorMessage(err, 'Invalid email or password') };
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
      await api.post('/auth/change-password', { current_password: current, new_password: next });
      clearSession();
      return { success: true };
    } catch (err: any) {
      return { success: false, error: errorMessage(err, 'Could not change the password.') };
    }
  };

  const markTourCompleted = useCallback(async () => {
    // Set here first so the tour does not restart before the server answers.
    updateSessionUser({ tour_completed_at: new Date().toISOString() });
    try {
      const res = await api.post<{ tour_completed_at: string }>('/auth/me/tour-completed');
      updateSessionUser({ tour_completed_at: res.data.tour_completed_at });
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
