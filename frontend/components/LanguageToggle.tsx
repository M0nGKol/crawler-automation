"use client";

import { useLocale } from "@/lib/i18n";

export default function LanguageToggle() {
  const { locale, setLocale } = useLocale();

  return (
    <button
      type="button"
      onClick={() => setLocale(locale === "ja" ? "en" : "ja")}
      className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition-all duration-300"
      style={{
        background: "rgba(129, 140, 248, 0.1)",
        border: "1px solid var(--color-border)",
        color: "var(--color-fuji)",
      }}
      aria-label="Toggle language"
    >
      <span
        style={{
          opacity: locale === "ja" ? 1 : 0.4,
          transition: "opacity 0.3s",
        }}
      >
        日本語
      </span>
      <span
        style={{
          width: "1px",
          height: "14px",
          background: "var(--color-border)",
        }}
      />
      <span
        style={{
          opacity: locale === "en" ? 1 : 0.4,
          transition: "opacity 0.3s",
        }}
      >
        EN
      </span>
    </button>
  );
}
