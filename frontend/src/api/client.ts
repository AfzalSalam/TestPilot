// A small fetch wrapper: attaches the bearer token, parses the standard error envelope,
// and signs the user out when the server says the session is no longer valid.

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api/v1";
const TOKEN_KEY = "tp.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: { field: string; message: string }[] | null,
  ) {
    super(message);
  }
  /** Map of field name -> message for form validation errors (HTTP 422). */
  get fieldErrors(): Record<string, string> {
    return Object.fromEntries((this.details ?? []).map((d) => [d.field, d.message]));
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn; };

type Query = Record<string, string | number | boolean | null | undefined>;

export async function request<T>(method: string, path: string, opts: { body?: unknown; query?: Query } = {}): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(opts.query ?? {})) if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));

  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  // Retry on network errors or Render hibernation (429 / 502 / 503 during cold starts)
  let res: Response | undefined;
  const maxAttempts = 6;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      res = await fetch(url, { method, headers, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined });

      // If Render is waking from hibernation, it returns 429 (hibernate-rate-limited) or 502/503/504
      const isHibernating = res.status === 429 || res.status === 502 || res.status === 503 || res.status === 504;
      if (isHibernating && attempt < maxAttempts - 1) {
        await new Promise((r) => setTimeout(r, 4000));
        continue;
      }
      break;
    } catch {
      if (attempt < maxAttempts - 1) {
        await new Promise((r) => setTimeout(r, 4000));
      }
    }
  }

  if (!res) {
    throw new ApiError(0, "network_error", "Cannot reach the server — it may be waking up. Please try again in a few seconds.");
  }

  if (res!.status === 204) return undefined as T;

  const data = await res!.json().catch(() => null);
  if (!res!.ok) {
    const err = data?.error;
    const error = new ApiError(res!.status, err?.code ?? "http_error", err?.message ?? res!.statusText, err?.details);
    if (res!.status === 401 && token && path !== "/auth/login") onUnauthorized();
    throw error;
  }
  return data as T;
}

export const http = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, { body: body ?? {} }),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, { body }),
  del: (path: string) => request<void>("DELETE", path),
};
