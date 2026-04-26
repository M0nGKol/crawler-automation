"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { login, setStoredToken } from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import LanguageToggle from "@/components/LanguageToggle";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useLocale();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await login(email, password);
      setStoredToken(data.token);
      localStorage.setItem("crawler_user_id", data.user_id);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("login.error"));
    } finally {
      setLoading(false);
    }
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
      {/* Language toggle top-right */}
      <div style={{ position: "fixed", top: "20px", right: "24px", zIndex: 10 }}>
        <LanguageToggle />
      </div>

      {/* Logo */}
      <div
        className="animate-fade-in"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "12px",
          marginBottom: "40px",
        }}
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

      {/* Login card */}
      <form
        onSubmit={onSubmit}
        className="glass-card-static animate-fade-in-delay-1"
        style={{
          width: "100%",
          maxWidth: "400px",
          padding: "36px 32px",
          display: "flex",
          flexDirection: "column",
          gap: "20px",
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

        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <label
            style={{ fontSize: "0.8rem", color: "var(--color-text-secondary)", fontWeight: 500 }}
          >
            {t("login.email")}
          </label>
          <input
            className="input-field"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <label
            style={{ fontSize: "0.8rem", color: "var(--color-text-secondary)", fontWeight: 500 }}
          >
            {t("login.password")}
          </label>
          <input
            className="input-field"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        <button type="submit" className="btn-sakura" disabled={loading} style={{ width: "100%" }}>
          {loading ? <span className="spinner" /> : t("login.submit")}
        </button>

        {error && (
          <p style={{ fontSize: "0.85rem", color: "var(--color-danger)", textAlign: "center" }}>
            {error}
          </p>
        )}

        <p
          style={{
            fontSize: "0.85rem",
            color: "var(--color-text-muted)",
            textAlign: "center",
          }}
        >
          {t("login.noAccount")}{" "}
          <Link
            href="/onboarding"
            style={{ color: "var(--color-sakura)", textDecoration: "none" }}
          >
            {t("login.startOnboarding")}
          </Link>
        </p>
      </form>
    </div>
  );
}
