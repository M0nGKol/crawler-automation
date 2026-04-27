"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useLocale } from "@/lib/i18n";
import LanguageToggle from "@/components/LanguageToggle";

const navItems = [
  { href: "/dashboard", icon: "◈", labelKey: "nav.dashboard" as const },
  { href: "/config", icon: "⚙", labelKey: "nav.config" as const },
  { href: "/logs", icon: "☰", labelKey: "nav.logs" as const },
  { href: "/users", icon: "◎", labelKey: "nav.users" as const },
];

export default function Sidebar({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useLocale();

  const handleLogout = () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("crawler_token");
    localStorage.removeItem("token");
    localStorage.removeItem("crawler_user_id");
    localStorage.removeItem("backend_user_id");
    localStorage.removeItem("user_id");
    document.cookie = "crawler_token=; Path=/; Max-Age=0";
    router.push("/login");
  };

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      {/* Sidebar */}
      <aside
        style={{
          width: "260px",
          flexShrink: 0,
          background: "var(--color-bg-primary)",
          borderRight: "1px solid var(--color-border)",
          display: "flex",
          flexDirection: "column",
          position: "fixed",
          top: 0,
          left: 0,
          bottom: 0,
          zIndex: 40,
        }}
      >
        {/* Logo area with seigaiha pattern */}
        <div
          className="bg-seigaiha"
          style={{
            padding: "24px 20px",
            borderBottom: "1px solid var(--color-border)",
          }}
        >
          <Link href="/dashboard" style={{ textDecoration: "none" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div
                style={{
                  width: "40px",
                  height: "40px",
                  borderRadius: "var(--radius-md)",
                  background:
                    "linear-gradient(135deg, var(--color-sakura), var(--color-fuji))",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "20px",
                }}
              >
                🏥
              </div>
              <div>
                <p
                  style={{
                    fontSize: "1rem",
                    fontWeight: 700,
                    color: "var(--color-text-primary)",
                    lineHeight: 1.2,
                  }}
                >
                  {t("app.title")}
                </p>
                <p
                  style={{
                    fontSize: "0.7rem",
                    color: "var(--color-text-muted)",
                    marginTop: "2px",
                  }}
                >
                  Health Care Crawler
                </p>
              </div>
            </div>
          </Link>
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: "16px 12px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {navItems.map((item) => {
              const isActive = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                    padding: "10px 14px",
                    borderRadius: "var(--radius-md)",
                    fontSize: "0.9rem",
                    fontWeight: isActive ? 600 : 400,
                    color: isActive
                      ? "var(--color-sakura)"
                      : "var(--color-text-secondary)",
                    background: isActive
                      ? "rgba(244, 114, 182, 0.08)"
                      : "transparent",
                    textDecoration: "none",
                    transition: "all 0.2s ease",
                    borderLeft: isActive
                      ? "3px solid var(--color-sakura)"
                      : "3px solid transparent",
                  }}
                >
                  <span style={{ fontSize: "1.1rem", width: "20px", textAlign: "center" }}>
                    {item.icon}
                  </span>
                  {t(item.labelKey)}
                </Link>
              );
            })}
          </div>
        </nav>

        {/* Bottom section */}
        <div
          style={{
            padding: "16px 12px",
            borderTop: "1px solid var(--color-border)",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "center" }}>
            <LanguageToggle />
          </div>
          <button
            onClick={handleLogout}
            type="button"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "8px 14px",
              background: "transparent",
              border: "none",
              borderRadius: "var(--radius-md)",
              color: "var(--color-text-muted)",
              cursor: "pointer",
              fontSize: "0.85rem",
              transition: "color 0.2s ease",
              width: "100%",
            }}
          >
            ↩ {t("nav.logout")}
          </button>
        </div>
      </aside>

      {/* Main content area */}
      <main
        style={{
          flex: 1,
          marginLeft: "260px",
          minHeight: "100vh",
          background: "var(--color-bg-deep)",
        }}
      >
        {children}
      </main>
    </div>
  );
}
