import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to attach Authorization Bearer token from localStorage
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('hp_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// An expired token used to fail silently. Every call 401'd, each caller showed
// its own empty state, and the dashboard simply went blank - indistinguishable
// from a broken feature, with nothing telling anyone to sign in again. So a 401
// is handled once, here, rather than eleven times in the features.
//
// The two keys cleared are the ones AuthProvider.logout clears; leaving a stale
// token behind would re-send it on the next call and 401 again.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const onLoginPage =
      typeof window !== 'undefined' && window.location.pathname.startsWith('/login');

    // Not on the login page: a 401 there is a wrong password, which the form
    // already reports, and redirecting would loop.
    if (error?.response?.status === 401 && typeof window !== 'undefined' && !onLoginPage) {
      localStorage.removeItem('hp_token');
      localStorage.removeItem('hp_user');
      window.location.href = '/login?expired=1';
    }
    return Promise.reject(error);
  }
);

export default api;
