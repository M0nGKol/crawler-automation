const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  "https://crawler-automation-1.onrender.com";

export type AuthLoginResponse = {
  token: string;
  user_id: string;
  email: string;
  company: string;
  role: string;
};

function authHeader(token?: string) {
  return token ? ({ Authorization: `Bearer ${token}` } as Record<string, string>) : ({} as Record<string, string>);
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token") || localStorage.getItem("crawler_token");
}

export function setStoredToken(token: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem("auth_token", token);
  localStorage.setItem("crawler_token", token);
  localStorage.setItem("token", token);
  document.cookie = `crawler_token=${token}; Path=/; SameSite=Lax`;
}

export async function apiFetch(path: string, options: RequestInit = {}) {
  const token = getStoredToken();
  const headers = new Headers(options.headers ?? {});
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("crawler_token");
    localStorage.removeItem("token");
    localStorage.removeItem("crawler_user_id");
    localStorage.removeItem("backend_user_id");
    localStorage.removeItem("user_id");
    document.cookie = "crawler_token=; Path=/; Max-Age=0";
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  return res;
}

export async function register(email: string, name: string, company: string, password: string) {
  const res = await apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, name, company, password }),
  });
  if (!res.ok) throw new Error("Registration failed");
  return (await res.json()) as { user_id: string; message: string };
}

export async function login(email: string, password: string): Promise<AuthLoginResponse> {
  const res = await apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Login failed");
  return (await res.json()) as AuthLoginResponse;
}

export async function getMe(token: string) {
  const res = await apiFetch("/auth/me", {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch user");
  return res.json();
}

export async function getGoogleAuthUrl(userId: string, returnTo?: string) {
  const query = new URLSearchParams({ user_id: userId });
  if (returnTo) query.set("return_to", returnTo);
  return { auth_url: `${API_URL}/auth/google?${query.toString()}` };
}

export async function getSheetsStatus(token: string) {
  const res = await apiFetch("/auth/sheets/status", {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch sheets status");
  return res.json();
}

export async function getStatus(token: string) {
  const res = await apiFetch("/status", {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

export async function getLogs(token: string) {
  const res = await apiFetch("/logs", {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch logs");
  return res.json();
}

export async function getSites(token: string) {
  const res = await apiFetch("/sites", {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch sites");
  return res.json();
}

export type SiteRecord = {
  id: string;
  site_name: string;
  url: string;
  type: string;
  is_default: boolean;
  is_active: boolean;
  mode?: string;
  last_run_at?: string | null;
};

export type RunStatus = {
  run_id: string;
  status: "running" | "completed" | "failed" | string;
  started_at: string | null;
  completed_at: string | null;
  jobs_found: number;
  sites_succeeded: number;
  sites_failed: number;
  sheet_url: string | null;
  errors?: string;
};

export async function getSitesList(token: string): Promise<{ sites: SiteRecord[] }> {
  const res = await apiFetch("/sites/list", {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch sites list");
  return res.json() as Promise<{ sites: SiteRecord[] }>;
}

export async function toggleSite(token: string, siteId: string, isActive: boolean) {
  const res = await apiFetch(`/sites/${siteId}`, {
    method: "PUT",
    headers: { ...authHeader(token) },
    body: JSON.stringify({ is_active: isActive }),
  });
  if (!res.ok) throw new Error("Failed to toggle site");
  return res.json() as Promise<SiteRecord>;
}

export async function addCustomSite(token: string, siteName: string, url: string) {
  const res = await apiFetch("/sites/add", {
    method: "POST",
    headers: { ...authHeader(token) },
    body: JSON.stringify({ site_name: siteName, url }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as Record<string, string>;
    throw new Error(err.detail ?? "Failed to add site");
  }
  return res.json() as Promise<SiteRecord>;
}

export async function startRun(token?: string): Promise<{ run_id: string; status: string }> {
  const res = await apiFetch("/run", {
    method: "POST",
    headers: { ...authHeader(token) },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error("Failed to trigger run");
  return res.json() as Promise<{ run_id: string; status: string }>;
}

export async function getRun(runId: string): Promise<RunStatus> {
  const res = await apiFetch(`/run/${runId}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch run status");
  return res.json() as Promise<RunStatus>;
}

// Keep the legacy triggerRun for any callers still using it
export async function triggerRun(token?: string) {
  return startRun(token);
}
