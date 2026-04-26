const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";

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
  return localStorage.getItem("crawler_token");
}

export function setStoredToken(token: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem("crawler_token", token);
  document.cookie = `crawler_token=${token}; Path=/; SameSite=Lax`;
}

export async function register(email: string, name: string, company: string, password: string) {
  const res = await fetch(`${BACKEND}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, name, company, password }),
  });
  if (!res.ok) throw new Error("Registration failed");
  return (await res.json()) as { user_id: string; message: string };
}

export async function login(email: string, password: string): Promise<AuthLoginResponse> {
  const res = await fetch(`${BACKEND}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Login failed");
  return (await res.json()) as AuthLoginResponse;
}

export async function getMe(token: string) {
  const res = await fetch(`${BACKEND}/auth/me`, {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch user");
  return res.json();
}

export async function getGoogleAuthUrl(userId: string) {
  const res = await fetch(`${BACKEND}/auth/google?user_id=${encodeURIComponent(userId)}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch Google OAuth URL");
  return (await res.json()) as { auth_url: string };
}

export async function getSheetsStatus(token: string) {
  const res = await fetch(`${BACKEND}/auth/sheets/status`, {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch sheets status");
  return res.json();
}

export async function triggerRun(token?: string) {
  const res = await fetch(`${BACKEND}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error("Failed to trigger run");
  return res.json();
}

export async function getStatus(token: string) {
  const res = await fetch(`${BACKEND}/status`, {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

export async function getLogs(token: string) {
  const res = await fetch(`${BACKEND}/logs`, {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch logs");
  return res.json();
}

export async function getSites(token: string) {
  const res = await fetch(`${BACKEND}/sites`, {
    headers: { ...authHeader(token) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch sites");
  return res.json();
}
