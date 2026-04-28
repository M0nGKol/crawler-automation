"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import { apiFetch, getGoogleAuthUrl, getMe, getSheetsStatus, getStoredToken } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

type ConnectionState = {
  connected: boolean;
  email?: string;
  sheet_id?: string | null;
  sheet_url?: string | null;
  role?: string;
  last_login?: string | null;
};

function getUserId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("crawler_user_id") || localStorage.getItem("backend_user_id");
}

async function ensureUserId(): Promise<string | null> {
  const existing = getUserId();
  if (existing) return existing;
  try {
    const sessionRes = await fetch("/api/auth/session", { cache: "no-store" });
    if (!sessionRes.ok) return null;
    const session = await sessionRes.json();
    const userId = session?.user_id as string | undefined;
    if (userId) localStorage.setItem("backend_user_id", userId);
    return userId ?? null;
  } catch {
    return null;
  }
}

export default function ConnectGoogle() {
  const { t } = useLocale();
  const pathname = usePathname();
  const [status, setStatus] = useState<ConnectionState>({ connected: false });
  const [loading, setLoading] = useState(false);
  const [testResult, setTestResult] = useState<string>("");

  const refreshStatus = useCallback(async () => {
    const token = getStoredToken();
    if (!token) {
      setStatus({ connected: false });
      return;
    }
    try {
      const data = await getMe(token);
      setStatus({
        connected: Boolean(data.sheet_id),
        email: data.email,
        sheet_id: data.sheet_id,
        sheet_url: data.sheet_url,
        role: data.role,
        last_login: data.last_login,
      });
    } catch {
      setStatus({ connected: false });
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const connectGoogle = async () => {
    setLoading(true);
    setTestResult("");
    try {
      const userId = await ensureUserId();
      if (!userId) throw new Error("Missing user id");
      const data = await getGoogleAuthUrl(userId, pathname || "/config");
      if (!data.auth_url) throw new Error("No auth URL returned");
      window.location.href = data.auth_url;
    } finally {
      setLoading(false);
    }
  };

  const disconnect = async () => {
    setLoading(true);
    try {
      const token = getStoredToken();
      if (!token) return;
      await apiFetch("/auth/disconnect", {
        method: "POST",
      });
      await refreshStatus();
    } finally {
      setLoading(false);
    }
  };

  const testConnection = async () => {
    setLoading(true);
    try {
      const token = getStoredToken();
      if (!token) {
        setTestResult(t("config.notConnected"));
        return;
      }
      const data = await getSheetsStatus(token);
      if (!data.connected) {
        setTestResult(t("config.notConnected"));
        return;
      }
      setTestResult(
        `✓ "${data.sheet_title}" · tabs: ${data.tab_count ?? 0}`,
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card-static" style={{ padding: "28px" }}>
      <h2
        style={{
          fontSize: "1.1rem",
          fontWeight: 600,
          color: "var(--color-text-primary)",
          marginBottom: "20px",
        }}
      >
        {t("config.sheetsConnection")}
      </h2>

      {status.connected ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span className="badge-success">● {t("dashboard.connected")}</span>
            <span style={{ fontSize: "0.85rem", color: "var(--color-text-secondary)" }}>
              {t("config.connectedAs")} {status.email}
            </span>
          </div>

          {status.sheet_url && (
            <a
              href={status.sheet_url}
              target="_blank"
              rel="noreferrer"
              style={{
                color: "var(--color-fuji)",
                fontSize: "0.85rem",
                wordBreak: "break-all",
              }}
            >
              📊 {status.sheet_url}
            </a>
          )}

          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <button onClick={disconnect} disabled={loading} className="btn-ghost btn-sm" type="button">
              {t("config.disconnect")}
            </button>
            <button onClick={testConnection} disabled={loading} className="btn-ghost btn-sm" type="button">
              {t("config.testConnection")}
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <p style={{ color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
            {t("config.notConnected")}
          </p>
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <button onClick={connectGoogle} disabled={loading} className="btn-fuji btn-sm" type="button">
              <svg viewBox="0 0 24 24" style={{ width: "16px", height: "16px", fill: "currentColor" }} aria-hidden>
                <path d="M21.35 11.1h-9.18v2.98h5.27c-.23 1.51-1.73 4.44-5.27 4.44-3.17 0-5.74-2.63-5.74-5.87s2.57-5.87 5.74-5.87c1.8 0 3.01.77 3.7 1.43l2.52-2.43C16.98 4.5 14.78 3.5 12.17 3.5 7.45 3.5 3.67 7.36 3.67 12.08s3.78 8.58 8.5 8.58c4.91 0 8.17-3.45 8.17-8.3 0-.56-.06-.98-.13-1.26Z" />
              </svg>
              {t("config.connect")}
            </button>
            <button onClick={testConnection} disabled={loading} className="btn-ghost btn-sm" type="button">
              {t("config.testConnection")}
            </button>
          </div>
        </div>
      )}

      {testResult && (
        <p
          style={{
            marginTop: "12px",
            fontSize: "0.85rem",
            color: testResult.startsWith("✓")
              ? "var(--color-jade)"
              : "var(--color-text-secondary)",
            padding: "10px 14px",
            background: "var(--color-bg-deep)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          {testResult}
        </p>
      )}
    </div>
  );
}
