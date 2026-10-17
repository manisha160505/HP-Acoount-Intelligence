export type UserRole = 'user' | 'admin' | 'super_admin';

/** Admin pages and admin-only features: the super admin is an admin too. */
export function isAdminRole(role: string | null | undefined): boolean {
  return role === 'admin' || role === 'super_admin';
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  /** True until the user replaces the password they were given. */
  must_change_password?: boolean;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}
