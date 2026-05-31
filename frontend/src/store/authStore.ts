// frontend/src/store/authStore.ts
const ACCESS_KEY = "choreo_access_token";
const REFRESH_KEY = "choreo_refresh_token";

export const authStore = {
  getAccessToken: () => localStorage.getItem(ACCESS_KEY),
  getRefreshToken: () => localStorage.getItem(REFRESH_KEY),
  setTokens: (access: string, refresh: string) => {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clearTokens: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
  isAuthenticated: () => !!localStorage.getItem(ACCESS_KEY),
};
