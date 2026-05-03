"use client";

import { useEffect, useState } from "react";

import LanguageToggle from "@/components/LanguageToggle";
import { useLocale } from "@/lib/i18n";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  "https://crawler-automation-1.onrender.com";

export default function LoginPage() {
  const { t } = useLocale();
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const err = params.get("error");
    if (err) setError(decodeURIComponent(err));
  }, []);

  const signInWithGoogle = () => {
    const params = new URLSearchParams({ return_to: "/dashboard" });
    window.location.href = `${API_URL}/auth/google?${params.toString()}`;
  };

  return (
    <div
      className="bg-seigaiha"
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
      }}
    >
      <div style={{ position: "fixed", top: "20px", right: "24px", zIndex: 10 }}>
        <LanguageToggle />
      </div>

      <div
        className="animate-fade-in"
        style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "40px" }}
      >
        <span style={{ fontSize: "32px" }}>🏥</span>
        <div>
          <p style={{ fontWeight: 700, fontSize: "1.3rem", color: "var(--color-text-primary)" }}>
            {t("app.title")}
          </p>
          <p style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
            Health Care Crawler
          </p>
        </div>
      </div>

      <div
        className="glass-card-static animate-fade-in-delay-1"
        style={{
          width: "100%",
          maxWidth: "400px",
          padding: "36px 32px",
          display: "flex",
          flexDirection: "column",
          gap: "24px",
          alignItems: "center",
        }}
      >
        <h1
          style={{
            fontSize: "1.4rem",
            fontWeight: 600,
            color: "var(--color-text-primary)",
            textAlign: "center",
          }}
        >
          {t("login.title")}
        </h1>

        <p style={{ fontSize: "0.9rem", color: "var(--color-text-secondary)", textAlign: "center" }}>
          Sign in with your Google account to get started. Your Google Sheets will be connected
          automatically.
        </p>

        <button
          onClick={signInWithGoogle}
          className="btn-fuji"
          type="button"
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "10px",
          }}
        >
          <svg
            viewBox="0 0 24 24"
            style={{ width: "18px", height: "18px", fill: "currentColor" }}
            aria-hidden
          >
            <path d="M21.35 11.1h-9.18v2.98h5.27c-.23 1.51-1.73 4.44-5.27 4.44-3.17 0-5.74-2.63-5.74-5.87s2.57-5.87 5.74-5.87c1.8 0 3.01.77 3.7 1.43l2.52-2.43C16.98 4.5 14.78 3.5 12.17 3.5 7.45 3.5 3.67 7.36 3.67 12.08s3.78 8.58 8.5 8.58c4.91 0 8.17-3.45 8.17-8.3 0-.56-.06-.98-.13-1.26Z" />
          </svg>
          Sign in with Google
        </button>

        {error && (
          <p style={{ fontSize: "0.85rem", color: "var(--color-danger)", textAlign: "center" }}>
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
