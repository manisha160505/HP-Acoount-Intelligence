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
  /** Seconds on the feature, from heartbeats. */
  time_seconds: number;
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
  time_seconds: number;
  top_feature: string | null;
  /** Every feature key, zeros included. */
  feature_views: Record<string, number>;
  feature_seconds: Record<string, number>;
}

export interface DailyPoint {
  date: string;
  active_users: number;
  views: number;
  time_seconds: number;
  /** Who was active that day (admin view). */
  user_ids?: string[];
}

export interface AccountViews {
  account_id: string;
  account_name: string | null;
  views: number;
  unique_users: number;
  user_ids?: string[];
}

export interface AnalyticsResponse {
  /** Inclusive UTC calendar dates, YYYY-MM-DD. */
  date_from: string;
  date_to: string;
  timezone: 'UTC';
  features: string[];
  totals: {
    total_users: number;
    active_users_7d: number;
    active_user_ids_7d?: string[];
    logins: number;
    feature_views: number;
    time_seconds: number;
  };
  per_feature: FeatureUsage[];
  per_user: UserUsage[];
  daily_active_users: DailyPoint[];
  top_accounts: AccountViews[];
}

/** GET /me/activity: the signed-in user's own usage. */
export interface MyActivityResponse {
  date_from: string;
  date_to: string;
  timezone: 'UTC';
  heartbeat_seconds: number;
  features: string[];
  totals: {
    logins: number;
    feature_views: number;
    time_seconds: number;
    features_used: number;
    top_feature: string | null;
    last_login_at: string | null;
  };
  per_feature: FeatureUsage[];
  daily: DailyPoint[];
  top_accounts: AccountViews[];
  recent: { ts: string; feature_key: string; account_id: string | null; account_name: string | null }[];
}
