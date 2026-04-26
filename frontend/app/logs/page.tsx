"use client";

import { useEffect, useState } from "react";

import { getLogs, getStoredToken } from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import Sidebar from "@/components/Sidebar";

type LogEntry = {
  id: string;
  started_at: string | null;
  finished_at: string | null;
  trigger: string | null;
  sites_attempted: number;
  sites_succeeded: number;
  listings_scraped: number;
  errors: string;
  sheet_url: string | null;
};

export default function LogsPage() {
  const { t } = useLocale();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const token = getStoredToken();
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const data = await getLogs(token);
        setLogs(data.logs ?? []);
      } catch {
        /* ignore */
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  return (
    <Sidebar>
      <div style={{ padding: "40px 36px" }}>
        <div className="animate-fade-in" style={{ marginBottom: "36px" }}>
          <h1
            style={{
              fontSize: "1.6rem",
              fontWeight: 700,
              color: "var(--color-text-primary)",
            }}
          >
            {t("logs.title")}
          </h1>
        </div>

        <div className="glass-card-static animate-fade-in-delay-1" style={{ overflow: "hidden" }}>
          {loading ? (
            <div
              style={{
                padding: "40px",
                display: "flex",
                justifyContent: "center",
              }}
            >
              <div className="spinner" />
            </div>
          ) : logs.length === 0 ? (
            <div
              style={{
                padding: "60px 24px",
                textAlign: "center",
                color: "var(--color-text-muted)",
              }}
            >
              <p style={{ fontSize: "2rem", marginBottom: "12px" }}>📋</p>
              <p style={{ fontSize: "0.95rem" }}>{t("logs.empty")}</p>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="table-jp">
                <thead>
                  <tr>
                    <th>{t("logs.date")}</th>
                    <th>{t("logs.trigger")}</th>
                    <th>{t("logs.sites")}</th>
                    <th>{t("logs.listings")}</th>
                    <th>{t("logs.status")}</th>
                    <th>{t("logs.sheetUrl")}</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => {
                    const hasErrors = Boolean(log.errors);
                    return (
                      <tr key={log.id}>
                        <td>
                          {log.started_at
                            ? new Date(log.started_at).toLocaleString("ja-JP", {
                                month: "short",
                                day: "numeric",
                                hour: "2-digit",
                                minute: "2-digit",
                              })
                            : "—"}
                        </td>
                        <td>
                          <span className="badge-neutral">{log.trigger ?? "—"}</span>
                        </td>
                        <td>
                          {log.sites_succeeded}/{log.sites_attempted}
                        </td>
                        <td>{log.listings_scraped}</td>
                        <td>
                          {hasErrors ? (
                            <span className="badge-danger">{t("logs.failed")}</span>
                          ) : (
                            <span className="badge-success">{t("logs.success")}</span>
                          )}
                        </td>
                        <td>
                          {log.sheet_url ? (
                            <a
                              href={log.sheet_url}
                              target="_blank"
                              rel="noreferrer"
                              style={{
                                color: "var(--color-fuji)",
                                fontSize: "0.8rem",
                                textDecoration: "none",
                              }}
                            >
                              📊 Open
                            </a>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </Sidebar>
  );
}
