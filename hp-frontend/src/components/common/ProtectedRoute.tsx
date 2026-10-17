'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/providers/AuthProvider';
import { UserRole, isAdminRole } from '@/types/auth';

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
}

// 'admin' in allowedRoles admits the super admin too.
function roleAllowed(role: UserRole, allowed?: UserRole[]): boolean {
  if (!allowed) return true;
  return allowed.includes(role) || (allowed.includes('admin') && isAdminRole(role));
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, allowedRoles }) => {
  const { user, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading) {
      if (!isAuthenticated) {
        router.push('/login');
      } else if (user?.must_change_password) {
        // A new account sets its own password before it can see anything.
        router.push('/change-password');
      } else if (user && !roleAllowed(user.role, allowedRoles)) {
        // Redirect unauthorized role to their designated homepage
        if (isAdminRole(user.role)) {
          router.push('/admin/home');
        } else {
          router.push('/user/home');
        }
      }
    }
  }, [isLoading, isAuthenticated, user, allowedRoles, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center space-y-3">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-hp-navy"></div>
          <p className="text-gray-600 text-sm font-medium">Verifying Enterprise Credentials...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  if (user?.must_change_password) return null;

  if (user && !roleAllowed(user.role, allowedRoles)) return null;

  return <>{children}</>;
};
