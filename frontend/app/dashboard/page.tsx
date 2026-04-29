"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  type RunStatus,
  type SiteRecord,
  addCustomSite,
  getMe,
  getRun,
  getSheetsStatus,
  getSitesList,
  getStatus,
  getStoredToken,
  startRun,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import Sidebar from "@/components/Sidebar";
import { SitesList } from "@/components/SitesList";

// ─────────────────────────────────────────────────────────────────────────────
// Add-site modal
// ─────────────────────────────────────────────────────────────────────────────
function AddSiteModal({
  onClose,
  onAdd,
}: {
  onClose: () => void;
  onAdd: (name: string, url: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !url.trim()) { setError("Both fields required"); return; }
    setLoading(true);
    setError("");
    try {
      await onAdd(name.trim(), url.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add site");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0,0,0,0.6)", display: "flex",
        alignItems: "center", justifyContent: "center",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="glass-card-static"
        style={{ padding: "32px", width: "100%", maxWidth: "420px", borderRadius: "16px" }}
      >
        <h2 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "20px", color: "var(--color-text-primary)" }}>
          Add Custom Site
        </h2>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <div>
            <label style={{ fontSize: "0.8rem", color: "var(--color-text-muted)", display: "block", marginBottom: "4px" }}>
              Site Name (slug)
            </label>
            <input
              id="add-site-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. my_hospital"
              style={{
                width: "100%", padding: "8px 12px", borderRadius: "8px",
                border: "1px solid var(--color-border, rgba(255,255,255,0.1))",
                background: "var(--color-surface, rgba(255,255,255,0.05))",
                color: "var(--color-text-primary)", fontSize: "0.9rem",
              }}
            />
          </div>
          <div>
            <label style={{ fontSize: "0.8rem", color: "var(--color-text-muted)", display: "block", marginBottom: "4px" }}>
              URL
            </label>
            <input
              id="add-site-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/jobs"
              style={{
                width: "100%", padding: "8px 12px", borderRadius: "8px",
                border: "1px solid var(--color-border, rgba(255,255,255,0.1))",
                background: "var(--color-surface, rgba(255,255,255,0.05))",
                color: "var(--color-text-primary)", fontSize: "0.9rem",
              }}
            />
          </div>
          {error && <p style={{ color: "var(--color-danger, #f87171)", fontSize: "0.85rem" }}>{error}</p>}
          <div style={{ display: "flex", gap: "10px", marginTop: "4px" }}>
            <button
              id="add-site-cancel"
              type="button"
              onClick={onClose}
              className="btn-ghost btn-sm"
              style={{ flex: 1 }}
            >
              Cancel
            </button>
            <button
              id="add-site-submit"
              type="submit"
              disabled={loading}
              className="btn-sakura btn-sm"
              style={{ flex: 1 }}
            >
              {loading ? "Adding…" : "Add Site"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Progress bar
// ─────────────────────────────────────────────────────────────────────────────
function ProgressBar({ label }: { label: string }) {
  return (
    <div style={{ marginTop: "16px" }}>
      <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)", marginBottom: "8px" }}>{label}</p>
      <div style={{
        height: "6px", borderRadius: "3px",
        background: "var(--color-surface, rgba(255,255,255,0.08))",
        overflow: "hidden",
      }}>
        <div style={{
          height: "100%", borderRadius: "3px",
          background: "linear-gradient(90deg, var(--color-sakura, #e879a0), var(--color-primary, #818cf8))",
          animation: "progress-indeterminate 1.6s ease-in-out infinite",
          width: "40%",
        }} />
      </div>
      <style>{`
        @keyframes progress-indeterminate {
          0% { transform: translateX(-200%); }
          100% { transform: translateX(500%); }
        }
      `}</style>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Dashboard
// ─────────────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { t } = useLocale();
  const [connected, setConnected] = useState(false);
  const [sheetTitle, setSheetTitle] = useState<string | null>(null);
  const [sheetUrl, setSheetUrl] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | null>(null);

  // Sites
  const [sites, setSites] = useState<SiteRecord[]>([]);
  const [sitesLoading, setSitesLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);

  // Run state
  const [running, setRunning] = useState(false);
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      const token = getStoredToken();
      if (!token) return;
      const [me, status, sheets] = await Promise.all([
        getMe(token).catch(() => null),
        getStatus(token).catch(() => null),
        getSheetsStatus(token).catch(() => null),
      ]);
      if (me) setUserName(me.name ?? me.email);
      if (status) setLastRun(status.last_run ?? null);
      if (sheets) {
        setConnected(Boolean(sheets.connected));
        setSheetTitle(sheets.sheet_title ?? null);
        setSheetUrl(sheets.sheet_url ?? null);
      }

      // Load sites list
      try {
        setSitesLoading(true);
        const { sites: siteList } = await getSitesList(token);
        setSites(siteList);
      } catch {
        /* non-fatal */
      } finally {
        setSitesLoading(false);
      }
    };
    void load();
  }, []);

  // ── Stop polling on unmount ───────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  // ── Add custom site ───────────────────────────────────────────────────────
  const handleAddSite = async (name: string, url: string) => {
    const token = getStoredToken();
    if (!token) throw new Error("Not logged in");
    const newSite = await addCustomSite(token, name, url);
    setSites((prev) => [...prev, newSite]);
  };

  // ── Run now with polling ─────────────────────────────────────────────────
  const handleRun = async () => {
    const token = getStoredToken();
    setRunning(true);
    setRunStatus(null);
    setRunError(null);

    try {
      const { run_id } = await startRun(token ?? undefined);

      // Poll every 3 seconds
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = setInterval(async () => {
        try {
          const status = await getRun(run_id);
          setRunStatus(status);
          if (status.status === "completed" || status.status === "failed") {
            clearInterval(pollIntervalRef.current!);
            pollIntervalRef.current = null;
            setRunning(false);
            if (status.status === "failed") setRunError(status.errors ?? t("dashboard.pollFailed"));
            // Refresh last run time
            const tok = getStoredToken();
            if (tok) {
              getStatus(tok).then((s) => setLastRun(s.last_run ?? null)).catch(() => null);
            }
          }
        } catch {
          clearInterval(pollIntervalRef.current!);
          pollIntervalRef.current = null;
          setRunning(false);
        }
      }, 3000);
    } catch (err) {
      setRunning(false);
      setRunError(err instanceof Error ? err.message : "Failed to start run");
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <Sidebar>
      {showAddModal && (
        <AddSiteModal
          onClose={() => setShowAddModal(false)}
          onAdd={handleAddSite}
        />
      )}

      <div style={{ padding: "40px 36px", maxWidth: "1100px" }}>
        {/* Header */}
        <div className="animate-fade-in" style={{ marginBottom: "36px" }}>
          <h1 style={{ fontSize: "1.6rem", fontWeight: 700, color: "var(--color-text-primary)" }}>
            {t("dashboard.title")}
          </h1>
          {userName && (
            <p style={{ fontSize: "0.9rem", color: "var(--color-text-muted)", marginTop: "4px" }}>{userName}</p>
          )}
        </div>

        {/* ── Top stats row ─────────────────────────────────────────────── */}
        <div
          className="animate-fade-in-delay-1"
          style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "20px", marginBottom: "28px" }}
        >
          {/* Sheets status */}
          <div className="glass-card-static" style={{ padding: "24px" }}>
            <p style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "8px" }}>
              Google Sheets
            </p>
            {connected ? (
              <span className="badge-success">● {t("dashboard.connected")}</span>
            ) : (
              <span className="badge-danger">● {t("dashboard.notConnected")}</span>
            )}
          </div>

          {/* Last run */}
          <div className="glass-card-static" style={{ padding: "24px" }}>
            <p style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "8px" }}>
              {t("dashboard.lastRun")}
            </p>
            <p style={{ fontSize: "1rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
              {lastRun
                ? new Date(lastRun).toLocaleString("ja-JP", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
                : t("dashboard.never")}
            </p>
          </div>

          {/* Run now */}
          <div className="glass-card-static" style={{ padding: "24px" }}>
            <p style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "12px" }}>
              {t("dashboard.runNow")}
            </p>
            <button
              id="run-now-btn"
              onClick={() => void handleRun()}
              disabled={running}
              className="btn-sakura btn-sm"
              type="button"
            >
              {running ? t("dashboard.running") : "▶ " + t("dashboard.runNow")}
            </button>
            {runError && (
              <p style={{ color: "var(--color-danger, #f87171)", fontSize: "0.8rem", marginTop: "8px" }}>{runError}</p>
            )}
            {running && <ProgressBar label="Pipeline is running…" />}
          </div>
        </div>

        {/* ── Run summary card (Task 11) ────────────────────────────────── */}
        {runStatus?.status === "completed" && (
          <div
            className="glass-card-static animate-fade-in"
            style={{ padding: "24px", marginBottom: "28px", borderLeft: "3px solid var(--color-success, #4ade80)" }}
          >
            <p style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "12px" }}>
              ✅ {t("dashboard.runSummary")}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "16px", marginBottom: "16px" }}>
              <div>
                <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>{t("dashboard.jobsFound")}</p>
                <p style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--color-text-primary)" }}>{runStatus.jobs_found}</p>
              </div>
              <div>
                <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>Sites succeeded</p>
                <p style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--color-success, #4ade80)" }}>{runStatus.sites_succeeded}</p>
              </div>
              <div>
                <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>Sites failed</p>
                <p style={{ fontSize: "1.4rem", fontWeight: 700, color: runStatus.sites_failed > 0 ? "var(--color-danger, #f87171)" : "var(--color-text-primary)" }}>{runStatus.sites_failed}</p>
              </div>
            </div>

            {/* Task 11: sheet tabs notice */}
            {runStatus.sheet_url && (
              <div style={{
                background: "rgba(255,255,255,0.04)", borderRadius: "10px",
                padding: "14px 16px", fontSize: "0.875rem",
                color: "var(--color-text-secondary)",
              }}>
                <p style={{ fontWeight: 600, marginBottom: "8px" }}>✅ {t("dashboard.sheetsNotice")}</p>
                <p>
                  → <strong>{t("dashboard.rawTab")}</strong>{" "}
                  <a
                    href={`${runStatus.sheet_url}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "var(--color-sakura, #e879a0)", textDecoration: "none" }}
                  >
                    {runStatus.jobs_found} jobs ({t("dashboard.unmasked")})
                  </a>
                </p>
                <p style={{ marginTop: "4px" }}>
                  → <strong>{t("dashboard.maskedTab")}</strong>{" "}
                  <a
                    href={`${runStatus.sheet_url}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "var(--color-sakura, #e879a0)", textDecoration: "none" }}
                  >
                    {runStatus.jobs_found} jobs ({t("dashboard.masked")})
                  </a>
                </p>
              </div>
            )}
          </div>
        )}

        {/* ── Sheet details ─────────────────────────────────────────────── */}
        <div className="animate-fade-in-delay-2" style={{ marginBottom: "28px" }}>
          {!connected ? (
            <div className="glass-card-static" style={{ padding: "24px", borderLeft: "3px solid var(--color-danger)" }}>
              <p style={{ color: "var(--color-text-secondary)", fontSize: "0.9rem" }}>
                {t("dashboard.notConnectedMsg")}
                {" — "}
                <Link href="/config" style={{ color: "var(--color-sakura)", textDecoration: "none" }}>
                  {t("nav.config")}
                </Link>
              </p>
            </div>
          ) : (
            <div className="glass-card-static" style={{ padding: "24px" }}>
              <p style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "12px" }}>
                {t("dashboard.sheetsStatus")}
              </p>
              <p style={{ fontSize: "1rem", fontWeight: 500, color: "var(--color-text-primary)", marginBottom: "8px" }}>
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

        {/* ── Sites list ─────────────────────────────────────────────────── */}
        <div className="animate-fade-in-delay-2">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
            <h2 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--color-text-primary)" }}>
              {t("dashboard.sites")}
            </h2>
            <button
              id="add-custom-site-btn"
              onClick={() => setShowAddModal(true)}
              className="btn-ghost btn-sm"
              type="button"
              style={{ fontSize: "0.8rem" }}
            >
              + {t("dashboard.addSite")}
            </button>
          </div>

          <div className="glass-card-static" style={{ padding: "16px" }}>
            {sitesLoading ? (
              <p style={{ color: "var(--color-text-muted)", fontSize: "0.9rem" }}>Loading sites…</p>
            ) : sites.length === 0 ? (
              <p style={{ color: "var(--color-text-muted)", fontSize: "0.9rem" }}>No sites found.</p>
            ) : (
              <SitesList sites={sites} />
            )}
          </div>
        </div>
      </div>
    </Sidebar>
  );
}
