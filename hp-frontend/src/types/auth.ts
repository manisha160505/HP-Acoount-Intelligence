export type UserRole = 'user' | 'admin';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}
