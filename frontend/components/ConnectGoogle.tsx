"use client";

import { useCallback, useEffect, useState } from "react";

import { getMe, getSheetsStatus, getStoredToken } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

type ConnectionState = {
  connected: boolean;
  email?: string;
  sheet_id?: string | null;
};

export default function ConnectGoogle() {
  const { t } = useLocale();
  const [status, setStatus] = useState<ConnectionState>({ connected: false });
  const [testResult, setTestResult] = useState<string>("");
  const [loading, setLoading] = useState(false);

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
      });
    } catch {
      setStatus({ connected: false });
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

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
      setTestResult(`✓ "${data.sheet_title}" · tabs: ${data.tab_count ?? 0}`);
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

          <button
            onClick={testConnection}
            disabled={loading}
            className="btn-ghost btn-sm"
            type="button"
            style={{ alignSelf: "flex-start" }}
          >
            {t("config.testConnection")}
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <p style={{ color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
            {t("config.notConnected")}
          </p>
          <p style={{ fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
            Sign out and sign back in with Google to reconnect.
          </p>
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
