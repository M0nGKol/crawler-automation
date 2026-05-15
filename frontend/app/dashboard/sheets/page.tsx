"use client";

import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import {
  type UserSheet,
  getSheets,
  createSheet,
  deleteSheet,
  setDefaultSheet,
  getStoredToken,
} from "@/lib/api";

// ─────────────────────────────────────────────────────────────────────────────
// Create sheet modal
// ─────────────────────────────────────────────────────────────────────────────
function CreateSheetModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (title: string) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Please enter a sheet name");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await onCreate(title.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create sheet");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <div
        className="glass-card-static"
        style={{ padding: "32px", width: "100%", maxWidth: "440px", borderRadius: "16px" }}
      >
        <h2 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "8px", color: "var(--color-text-primary)" }}>
          Create New Sheet
        </h2>
        <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)", marginBottom: "24px" }}>
          A new Google Sheet will be created in your Google Drive with the standard Jobs Raw, Jobs Masked, and Run Log tabs.
        </p>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <div>
            <label style={{ fontSize: "0.8rem", color: "var(--color-text-muted)", display: "block", marginBottom: "6px" }}>
              Sheet Name
            </label>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Client A — Tokyo Nurses"
              style={{
                width: "100%", padding: "10px 12px", borderRadius: "8px",
                border: "1px solid var(--color-border, rgba(255,255,255,0.1))",
                background: "var(--color-surface, rgba(255,255,255,0.05))",
                color: "var(--color-text-primary)", fontSize: "0.9rem",
                boxSizing: "border-box",
              }}
            />
          </div>

          {error && (
            <p style={{ color: "var(--color-danger, #f87171)", fontSize: "0.85rem" }}>{error}</p>
          )}

          <div style={{ display: "flex", gap: "10px", marginTop: "4px" }}>
            <button type="button" onClick={onClose} className="btn-ghost btn-sm" style={{ flex: 1 }}>
              Cancel
            </button>
            <button type="submit" disabled={loading} className="btn-sakura btn-sm" style={{ flex: 1 }}>
              {loading ? "Creating…" : "Create Sheet"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sheet card
// ─────────────────────────────────────────────────────────────────────────────
function SheetCard({
  sheet,
  onSetDefault,
  onDelete,
  isOnlySheet,
}: {
  sheet: UserSheet;
  onSetDefault: (id: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  isOnlySheet: boolean;
}) {
  const [settingDefault, setSettingDefault] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleSetDefault = async () => {
    setSettingDefault(true);
    try {
      await onSetDefault(sheet.id);
    } finally {
      setSettingDefault(false);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setDeleting(true);
    try {
      await onDelete(sheet.id);
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  return (
    <div
      className="glass-card-static"
      style={{
        padding: "20px 24px",
        borderRadius: "12px",
        border: sheet.is_default
          ? "1px solid rgba(244,114,182,0.4)"
          : "1px solid var(--color-border, rgba(255,255,255,0.08))",
        display: "flex",
        alignItems: "center",
        gap: "16px",
        transition: "border-color 0.2s",
      }}
    >
      {/* Icon */}
      <div style={{
        width: "44px", height: "44px", borderRadius: "10px", flexShrink: 0,
        background: sheet.is_default
          ? "linear-gradient(135deg, var(--color-sakura, #e879a0), var(--color-fuji, #818cf8))"
          : "rgba(255,255,255,0.06)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: "1.3rem",
      }}>
        📊
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
          <p style={{
            fontWeight: 600, fontSize: "0.95rem",
            color: "var(--color-text-primary)",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {sheet.sheet_title || "Untitled Sheet"}
          </p>
          {sheet.is_default && (
            <span style={{
              fontSize: "0.7rem", fontWeight: 700, padding: "2px 8px",
              borderRadius: "999px", letterSpacing: "0.04em",
              background: "rgba(244,114,182,0.15)",
              color: "var(--color-sakura, #e879a0)",
              border: "1px solid rgba(244,114,182,0.3)",
              flexShrink: 0,
            }}>
              DEFAULT
            </span>
          )}
        </div>
        <a
          href={sheet.sheet_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            fontSize: "0.78rem", color: "var(--color-text-muted)",
            textDecoration: "none", fontFamily: "monospace",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "var(--color-sakura, #e879a0)")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "var(--color-text-muted)")}
        >
          ↗ Open in Google Sheets
        </a>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: "8px", flexShrink: 0 }}>
        {!sheet.is_default && (
          <button
            onClick={handleSetDefault}
            disabled={settingDefault}
            className="btn-ghost btn-sm"
            style={{ fontSize: "0.8rem", padding: "6px 12px" }}
          >
            {settingDefault ? "Setting…" : "Set Default"}
          </button>
        )}

        {!isOnlySheet && !sheet.is_default && (
          <button
            onClick={handleDelete}
            disabled={deleting}
            style={{
              fontSize: "0.8rem", padding: "6px 12px",
              borderRadius: "6px", border: "none", cursor: "pointer",
              background: confirmDelete ? "rgba(248,113,113,0.2)" : "transparent",
              color: confirmDelete ? "#f87171" : "var(--color-text-muted)",
              transition: "all 0.2s",
            }}
            onMouseEnter={(e) => {
              if (!confirmDelete) e.currentTarget.style.color = "#f87171";
            }}
            onMouseLeave={(e) => {
              if (!confirmDelete) e.currentTarget.style.color = "var(--color-text-muted)";
            }}
          >
            {deleting ? "Removing…" : confirmDelete ? "Confirm remove?" : "Remove"}
          </button>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────
export default function SheetsPage() {
  const [sheets, setSheets] = useState<UserSheet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [actionError, setActionError] = useState("");

  const token = getStoredToken() ?? "";

  const fetchSheets = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getSheets(token);
      setSheets(data.sheets);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sheets");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSheets();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = async (title: string) => {
    setActionError("");
    const newSheet = await createSheet(token, title);
    setSheets((prev) => [...prev, newSheet]);
  };

  const handleSetDefault = async (id: string) => {
    setActionError("");
    try {
      const updated = await setDefaultSheet(token, id);
      setSheets((prev) =>
        prev.map((s) => ({ ...s, is_default: s.id === updated.id }))
      );
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to set default");
    }
  };

  const handleDelete = async (id: string) => {
    setActionError("");
    try {
      await deleteSheet(token, id);
      setSheets((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to remove sheet");
    }
  };

  return (
    <Sidebar>
      <div style={{ padding: "40px", maxWidth: "800px" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "32px" }}>
          <div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--color-text-primary)", marginBottom: "6px" }}>
              Google Sheets
            </h1>
            <p style={{ fontSize: "0.9rem", color: "var(--color-text-muted)" }}>
              Manage the sheets that scraped data gets written to. Each sheet gets its own{" "}
              <strong style={{ color: "var(--color-text-secondary)" }}>Jobs Raw</strong> and{" "}
              <strong style={{ color: "var(--color-text-secondary)" }}>Jobs Masked</strong> tabs.
            </p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-sakura btn-sm"
            style={{ flexShrink: 0, marginLeft: "24px", padding: "10px 18px", fontSize: "0.9rem" }}
          >
            + New Sheet
          </button>
        </div>

        {/* Info banner */}
        <div style={{
          padding: "14px 18px", borderRadius: "10px", marginBottom: "28px",
          background: "rgba(129,140,248,0.08)", border: "1px solid rgba(129,140,248,0.2)",
          fontSize: "0.85rem", color: "var(--color-text-secondary)",
          display: "flex", gap: "10px", alignItems: "flex-start",
        }}>
          <span style={{ flexShrink: 0, marginTop: "1px" }}>ℹ</span>
          <span>
            The <strong>Default</strong> sheet is where the pipeline writes data during every run.
            You can override this per-run from the dashboard. Removing a sheet only removes it from
            this list — it stays in your Google Drive.
          </span>
        </div>

        {/* Action error */}
        {actionError && (
          <div style={{
            padding: "12px 16px", borderRadius: "8px", marginBottom: "20px",
            background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.3)",
            color: "#f87171", fontSize: "0.85rem",
          }}>
            {actionError}
          </div>
        )}

        {/* Sheet list */}
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {[1, 2].map((i) => (
              <div
                key={i}
                style={{
                  height: "84px", borderRadius: "12px",
                  background: "rgba(255,255,255,0.04)",
                  animation: "pulse 1.5s ease-in-out infinite",
                }}
              />
            ))}
            <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>
          </div>
        ) : error ? (
          <div style={{
            padding: "24px", borderRadius: "12px", textAlign: "center",
            background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.2)",
            color: "#f87171", fontSize: "0.9rem",
          }}>
            {error}
            <button onClick={fetchSheets} className="btn-ghost btn-sm" style={{ display: "block", margin: "12px auto 0" }}>
              Retry
            </button>
          </div>
        ) : sheets.length === 0 ? (
          <div style={{
            padding: "48px 24px", borderRadius: "12px", textAlign: "center",
            background: "rgba(255,255,255,0.03)", border: "1px dashed var(--color-border, rgba(255,255,255,0.1))",
          }}>
            <p style={{ fontSize: "2rem", marginBottom: "12px" }}>📊</p>
            <p style={{ fontSize: "1rem", fontWeight: 600, color: "var(--color-text-primary)", marginBottom: "6px" }}>
              No sheets yet
            </p>
            <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)", marginBottom: "20px" }}>
              Create your first sheet to start writing scraped data.
            </p>
            <button onClick={() => setShowCreateModal(true)} className="btn-sakura btn-sm">
              + Create Sheet
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {/* Default sheet always shown first */}
            {[...sheets].sort((a, b) => (b.is_default ? 1 : 0) - (a.is_default ? 1 : 0)).map((sheet) => (
              <SheetCard
                key={sheet.id}
                sheet={sheet}
                onSetDefault={handleSetDefault}
                onDelete={handleDelete}
                isOnlySheet={sheets.length === 1}
              />
            ))}
          </div>
        )}

        {/* Sheet count footer */}
        {sheets.length > 0 && (
          <p style={{ fontSize: "0.8rem", color: "var(--color-text-muted)", marginTop: "20px" }}>
            {sheets.length} sheet{sheets.length !== 1 ? "s" : ""} connected
          </p>
        )}
      </div>

      {showCreateModal && (
        <CreateSheetModal
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreate}
        />
      )}
    </Sidebar>
  );
}
