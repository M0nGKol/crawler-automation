"use client";

import { useLocale } from "@/lib/i18n";
import Sidebar from "@/components/Sidebar";
import ConnectGoogle from "@/components/ConnectGoogle";

export default function ConfigPage() {
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
            {t("config.title")}
          </h1>
        </div>

        <div className="animate-fade-in-delay-1">
          <ConnectGoogle />
        </div>
      </div>
    </Sidebar>
  );
}
