const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const ACCESS_TOKEN_KEY = "careguard.demoAccessToken";


export function apiUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}


export function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const accessToken = window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
  if (accessToken) headers.set("X-Demo-Access-Token", accessToken);
  return fetch(apiUrl(path), { ...options, headers });
}


export { ACCESS_TOKEN_KEY };
