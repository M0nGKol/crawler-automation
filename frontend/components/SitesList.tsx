"use client";

import { useEffect, useState } from "react";
import { type SiteRecord, getStoredToken, toggleSite } from "@/lib/api";

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      disabled={disabled}
      style={{
        width: "44px",
        height: "24px",
        borderRadius: "12px",
        border: "none",
        cursor: disabled ? "not-allowed" : "pointer",
        background: checked
          ? "linear-gradient(135deg, var(--color-sakura, #e879a0), var(--color-sakura-vivid, #db2777))"
          : "rgba(255,255,255,0.12)",
        position: "relative",
        transition: "background 0.2s ease",
        flexShrink: 0,
        opacity: disabled ? 0.6 : 1,
        padding: 0,
      }}
    >
      <span
        style={{
          position: "absolute",
          top: "3px",
          left: checked ? "23px" : "3px",
          width: "18px",
          height: "18px",
          borderRadius: "50%",
          background: "white",
          transition: "left 0.2s ease",
          boxShadow: "0 1px 3px rgba(0,0,0,0.35)",
          display: "block",
        }}
      />
    </button>
  );
}

const COL_HEADERS = ["SITE NAME", "URL", "TYPE", "LAST RUN", "ACTIVE"] as const;

export function SitesList({ sites: propSites }: { sites: SiteRecord[] }) {
  const [sites, setSites] = useState<SiteRecord[]>(propSites);
  const [toggling, setToggling] = useState<string | null>(null);

  useEffect(() => {
    setSites(propSites);
  }, [propSites]);

  const handleToggle = async (site: SiteRecord) => {
    if (toggling) return;
    const newActive = !site.is_active;

    setSites((prev) =>
      prev.map((s) => (s.id === site.id ? { ...s, is_active: newActive } : s)),
    );
    setToggling(site.id);

    try {
      const token = getStoredToken();
      if (!token) throw new Error("Not authenticated");
      await toggleSite(token, site.id, newActive);
    } catch {
      setSites((prev) =>
        prev.map((s) => (s.id === site.id ? { ...s, is_active: site.is_active } : s)),
      );
    } finally {
      setToggling(null);
    }
  };

  if (sites.length === 0) {
    return (
      <p style={{ color: "var(--color-text-muted)", fontSize: "0.9rem", padding: "8px 4px" }}>
        No sites configured.
      </p>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
        <thead>
          <tr>
            {COL_HEADERS.map((col) => (
              <th
                key={col}
                style={{
                  padding: "8px 14px",
                  textAlign: "left",
                  fontSize: "0.68rem",
                  fontWeight: 600,
                  color: "var(--color-text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.07em",
                  borderBottom: "1px solid rgba(255,255,255,0.07)",
                  whiteSpace: "nowrap",
                }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sites.map((site) => (
            <tr
              key={site.id}
              style={{
                borderBottom: "1px solid rgba(255,255,255,0.04)",
                transition: "background 0.15s ease",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLTableRowElement).style.background =
                  "rgba(255,255,255,0.03)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLTableRowElement).style.background = "transparent";
              }}
            >
              {/* Site name */}
              <td
                style={{
                  padding: "12px 14px",
                  fontWeight: 500,
                  color: "var(--color-text-primary)",
                  whiteSpace: "nowrap",
                }}
              >
                {site.site_name}
              </td>

              {/* URL */}
              <td
                style={{
                  padding: "12px 14px",
                  color: "var(--color-text-muted)",
                  maxWidth: "240px",
                }}
              >
                <span
                  title={site.url}
                  style={{
                    display: "block",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    fontSize: "0.82rem",
                  }}
                >
                  {site.url}
                </span>
              </td>

              {/* Type badge */}
              <td style={{ padding: "12px 14px", whiteSpace: "nowrap" }}>
                <span
                  style={{
                    fontSize: "0.68rem",
                    fontWeight: 700,
                    padding: "3px 9px",
                    borderRadius: "5px",
                    background: site.is_default
                      ? "rgba(129,140,248,0.15)"
                      : "rgba(232,121,169,0.15)",
                    color: site.is_default
                      ? "var(--color-fuji, #818cf8)"
                      : "var(--color-sakura, #e879a0)",
                    textTransform: "uppercase",
                    letterSpacing: "0.04em",
                  }}
                >
                  {site.is_default ? "Default" : "Custom"}
                </span>
              </td>

              {/* Last run */}
              <td
                style={{
                  padding: "12px 14px",
                  color: "var(--color-text-muted)",
                  fontSize: "0.82rem",
                  whiteSpace: "nowrap",
                }}
              >
                {site.last_run_at
                  ? new Date(site.last_run_at).toLocaleString("ja-JP", {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "—"}
              </td>

              {/* Toggle */}
              <td style={{ padding: "12px 14px" }}>
                <Toggle
                  checked={site.is_active}
                  onChange={() => void handleToggle(site)}
                  disabled={toggling === site.id}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
