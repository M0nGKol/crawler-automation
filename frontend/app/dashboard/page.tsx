"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getMe, getSheetsStatus, getStatus, getStoredToken, triggerRun } from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import Sidebar from "@/components/Sidebar";

export default function DashboardPage() {
  const { t } = useLocale();
  const [connected, setConnected] = useState(false);
  const [sheetTitle, setSheetTitle] = useState<string | null>(null);
  const [sheetUrl, setSheetUrl] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    const load = async () => {
      const token = getStoredToken();
      if (!token) return;
      const me = await getMe(token);
      setUserName(me.name ?? me.email);
      const status = await getStatus(token);
      const sheets = await getSheetsStatus(token);
      setLastRun(status.last_run ?? null);
      setConnected(Boolean(sheets.connected));
      setSheetTitle(sheets.sheet_title ?? null);
      setSheetUrl(sheets.sheet_url ?? null);
    };
    void load().catch(() => {
      setConnected(false);
      setSheetTitle(null);
      setSheetUrl(null);
    });
  }, []);

  const handleRun = async () => {
    setRunning(true);
    try {
      const token = getStoredToken();
      await triggerRun(token ?? undefined);
    } catch {
      /* handled by UI */
    } finally {
      setRunning(false);
    }
  };

  return (
    <Sidebar>
      <div style={{ padding: "40px 36px", maxWidth: "1000px" }}>
        {/* Header */}
        <div className="animate-fade-in" style={{ marginBottom: "36px" }}>
          <h1
            style={{
              fontSize: "1.6rem",
              fontWeight: 700,
              color: "var(--color-text-primary)",
            }}
          >
            {t("dashboard.title")}
          </h1>
          {userName && (
            <p style={{ fontSize: "0.9rem", color: "var(--color-text-muted)", marginTop: "4px" }}>
              {userName}
            </p>
          )}
        </div>

        {/* Stats row */}
        <div
          className="animate-fade-in-delay-1"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "20px",
            marginBottom: "28px",
          }}
        >
          {/* Sheets status card */}
          <div className="glass-card-static" style={{ padding: "24px" }}>
            <p
              style={{
                fontSize: "0.75rem",
                fontWeight: 600,
                color: "var(--color-text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: "8px",
              }}
            >
              Google Sheets
            </p>
            {connected ? (
              <span className="badge-success">● {t("dashboard.connected")}</span>
            ) : (
              <span className="badge-danger">● {t("dashboard.notConnected")}</span>
            )}
          </div>

          {/* Last run card */}
          <div className="glass-card-static" style={{ padding: "24px" }}>
            <p
              style={{
                fontSize: "0.75rem",
                fontWeight: 600,
                color: "var(--color-text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: "8px",
              }}
            >
              {t("dashboard.lastRun")}
            </p>
            <p
              style={{
                fontSize: "1rem",
                fontWeight: 600,
                color: "var(--color-text-primary)",
              }}
            >
              {lastRun
                ? new Date(lastRun).toLocaleString("ja-JP", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : t("dashboard.never")}
            </p>
          </div>

          {/* Run now card */}
          <div className="glass-card-static" style={{ padding: "24px" }}>
            <p
              style={{
                fontSize: "0.75rem",
                fontWeight: 600,
                color: "var(--color-text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: "12px",
              }}
            >
              {t("dashboard.runNow")}
            </p>
            <button
              onClick={handleRun}
              disabled={running}
              className="btn-sakura btn-sm"
              type="button"
            >
              {running ? t("dashboard.running") : "▶ " + t("dashboard.runNow")}
            </button>
          </div>
        </div>

        {/* Sheet details */}
        <div className="animate-fade-in-delay-2">
          {!connected ? (
            <div
              className="glass-card-static"
              style={{
                padding: "24px",
                borderLeft: "3px solid var(--color-danger)",
              }}
            >
              <p style={{ color: "var(--color-text-secondary)", fontSize: "0.9rem" }}>
                {t("dashboard.notConnectedMsg")}
                {" — "}
                <Link
                  href="/config"
                  style={{ color: "var(--color-sakura)", textDecoration: "none" }}
                >
                  {t("nav.config")}
                </Link>
              </p>
            </div>
          ) : (
            <div className="glass-card-static" style={{ padding: "24px" }}>
              <p
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  color: "var(--color-text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  marginBottom: "12px",
                }}
              >
                {t("dashboard.sheetsStatus")}
              </p>
              <p
                style={{
                  fontSize: "1rem",
                  fontWeight: 500,
                  color: "var(--color-text-primary)",
                  marginBottom: "8px",
                }}
              >
                {sheetTitle}
              </p>
              {sheetUrl && (
                <a
                  href={sheetUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-ghost btn-sm"
                  style={{ textDecoration: "none", marginTop: "8px", display: "inline-flex" }}
                >
                  📊 {t("dashboard.viewSheet")}
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </Sidebar>
  );
}
