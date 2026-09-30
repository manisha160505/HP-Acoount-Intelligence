import { UserRole } from '@/types/auth';

/** GET /admin/users row. Never carries a password or hash. */
export interface ManagedUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface FeatureUsage {
  feature_key: string;
  unique_users: number;
  total_views: number;
  last_used_at: string | null;
}

export interface UserUsage {
  user_id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  last_login_at: string | null;
  logins: number;
  features_used: number;
  top_feature: string | null;
  /** Every feature key, zeros included. */
  feature_views: Record<string, number>;
}

export interface AnalyticsResponse {
  /** Inclusive UTC calendar dates, YYYY-MM-DD. */
  date_from: string;
  date_to: string;
  timezone: 'UTC';
  features: string[];
  totals: { total_users: number; active_users_7d: number; logins: number; feature_views: number };
  per_feature: FeatureUsage[];
  per_user: UserUsage[];
  daily_active_users: { date: string; active_users: number }[];
  top_accounts: { account_id: string; account_name: string | null; views: number; unique_users: number }[];
}
