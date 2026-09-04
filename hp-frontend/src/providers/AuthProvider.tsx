'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { User, AuthState } from '@/types/auth';
import api from '@/services/api';

interface AuthContextType extends AuthState {
  login: (email: string, pass: string) => Promise<{ success: boolean; role?: string; error?: string }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const storedToken = localStorage.getItem('hp_token');
    const storedUser = localStorage.getItem('hp_user');

    if (storedToken && storedUser) {
      setToken(storedToken);
      try {
        setUser(JSON.parse(storedUser));
      } catch (e) {
        localStorage.removeItem('hp_token');
        localStorage.removeItem('hp_user');
      }
    }
    setIsLoading(false);
  }, []);

  const login = async (email: string, pass: string) => {
    try {
      const response = await api.post('/auth/login', { email, password: pass });
      const { access_token, user: userData } = response.data;

      localStorage.setItem('hp_token', access_token);
      localStorage.setItem('hp_user', JSON.stringify(userData));

      setToken(access_token);
      setUser(userData);

      return { success: true, role: userData.role };
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Invalid email or password';
      return { success: false, error: errorMsg };
    }
  };

  const logout = () => {
    localStorage.removeItem('hp_token');
    localStorage.removeItem('hp_user');
    setToken(null);
    setUser(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!token && !!user,
        login,
        logout,
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
