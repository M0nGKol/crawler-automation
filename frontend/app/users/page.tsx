"use client";

import { useLocale } from "@/lib/i18n";
import Sidebar from "@/components/Sidebar";

export default function UsersPage() {
  const { t } = useLocale();

  return (
    <Sidebar>
      <div style={{ padding: "40px 36px", maxWidth: "800px" }}>
        <div className="animate-fade-in" style={{ marginBottom: "36px" }}>
          <h1
            style={{
              fontSize: "1.6rem",
              fontWeight: 700,
              color: "var(--color-text-primary)",
            }}
          >
            {t("users.title")}
          </h1>
        </div>

        <div
          className="glass-card-static animate-fade-in-delay-1"
          style={{
            padding: "60px 24px",
            textAlign: "center",
          }}
        >
          <p style={{ fontSize: "2.5rem", marginBottom: "16px" }}>👥</p>
          <p
            style={{
              fontSize: "1rem",
              color: "var(--color-text-muted)",
              lineHeight: 1.7,
            }}
          >
            {t("users.empty")}
          </p>
        </div>
      </div>
    </Sidebar>
  );
}
