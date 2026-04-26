"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { getGoogleAuthUrl, register } from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import LanguageToggle from "@/components/LanguageToggle";

type ProgressState = "pending" | "active" | "done";

export default function OnboardingPage() {
  const router = useRouter();
  const { t } = useLocale();
  const [step, setStep] = useState(1);
  const [company, setCompany] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [userId, setUserId] = useState("");
  const [sheetUrl, setSheetUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const progressKeys = useMemo(
    () => [
      "onboarding.progress.0" as const,
      "onboarding.progress.1" as const,
      "onboarding.progress.2" as const,
      "onboarding.progress.3" as const,
      "onboarding.progress.4" as const,
    ],
    [],
  );

  const [progress, setProgress] = useState<ProgressState[]>(
    Array(progressKeys.length).fill("pending"),
  );

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (!event.data) return;
      if (event.data.success) {
        setSheetUrl(event.data.sheet_url ?? "");
        setStep(3);
      } else if (event.data.error) {
        setError(String(event.data.error));
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  useEffect(() => {
    if (step !== 3) return;
    progressKeys.forEach((_, index) => {
      setTimeout(() => {
        setProgress((prev) =>
          prev.map((value, i) => {
            if (i < index) return "done";
            if (i === index) return "active";
            return "pending";
          }),
        );
      }, index * 1000);
      setTimeout(() => {
        setProgress((prev) => prev.map((value, i) => (i <= index ? "done" : value)));
      }, index * 1000 + 700);
    });

    const endTimeout = setTimeout(() => setStep(4), 4000);
    return () => clearTimeout(endTimeout);
  }, [step, progressKeys]);

  const stepLabels = useMemo(
    () => [
      "onboarding.step1" as const,
      "onboarding.step2" as const,
      "onboarding.step3" as const,
      "onboarding.step4" as const,
    ],
    [],
  );

  const submitRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await register(email, name, company, password);
      setUserId(res.user_id);
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("onboarding.error.register"));
    } finally {
      setLoading(false);
    }
  };

  const connectGoogle = async () => {
    setError("");
    setLoading(true);
    try {
      const data = await getGoogleAuthUrl(userId);
      window.open(data.auth_url, "google-auth", "width=500,height=600");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("onboarding.error.google"));
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
        padding: "40px 24px",
      }}
    >
      {/* Language toggle */}
      <div style={{ position: "fixed", top: "20px", right: "24px", zIndex: 10 }}>
        <LanguageToggle />
      </div>

      {/* Title */}
      <div className="animate-fade-in" style={{ textAlign: "center", marginBottom: "40px" }}>
        <h1
          style={{
            fontSize: "1.6rem",
            fontWeight: 700,
            color: "var(--color-text-primary)",
          }}
        >
          {t("onboarding.title")}
        </h1>
      </div>

      {/* Step indicator */}
      <div
        className="animate-fade-in-delay-1"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0",
          marginBottom: "40px",
          maxWidth: "500px",
          width: "100%",
          justifyContent: "center",
        }}
      >
        {stepLabels.map((labelKey, index) => {
          const s = index + 1;
          const isDone = step > s;
          const isActive = step === s;
          return (
            <div key={labelKey} style={{ display: "flex", alignItems: "center" }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.85rem",
                    fontWeight: 600,
                    transition: "all 0.3s ease",
                    background: isDone
                      ? "var(--color-jade)"
                      : isActive
                        ? "linear-gradient(135deg, var(--color-sakura), var(--color-sakura-vivid))"
                        : "var(--color-bg-surface)",
                    color: isDone || isActive ? "white" : "var(--color-text-muted)",
                    boxShadow: isActive ? "0 0 16px var(--color-sakura-glow)" : "none",
                  }}
                >
                  {isDone ? "✓" : s}
                </div>
                <p
                  style={{
                    fontSize: "0.7rem",
                    color: isActive ? "var(--color-sakura)" : "var(--color-text-muted)",
                    marginTop: "6px",
                    textAlign: "center",
                    whiteSpace: "nowrap",
                  }}
                >
                  {t(labelKey)}
                </p>
              </div>
              {index < stepLabels.length - 1 && (
                <div
                  style={{
                    width: "40px",
                    height: "2px",
                    background:
                      step > s + 1
                        ? "var(--color-jade)"
                        : step > s
                          ? "var(--color-sakura)"
                          : "var(--color-bg-elevated)",
                    margin: "0 8px",
                    marginBottom: "22px",
                    transition: "background 0.3s ease",
                  }}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Step content */}
      <div style={{ width: "100%", maxWidth: "480px" }}>
        {/* Step 1: Register */}
        {step === 1 && (
          <form
            onSubmit={submitRegister}
            className="glass-card-static animate-fade-in"
            style={{
              padding: "32px 28px",
              display: "flex",
              flexDirection: "column",
              gap: "18px",
            }}
          >
            <h2
              style={{
                fontSize: "1.1rem",
                fontWeight: 600,
                color: "var(--color-text-primary)",
              }}
            >
              {t("onboarding.step1")}
            </h2>

            <input
              className="input-field"
              placeholder={t("onboarding.company")}
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              required
            />
            <input
              className="input-field"
              placeholder={t("onboarding.name")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
            <input
              className="input-field"
              type="email"
              placeholder={t("onboarding.email")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <input
              className="input-field"
              type="password"
              placeholder={t("onboarding.password")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button type="submit" className="btn-sakura" disabled={loading} style={{ width: "100%" }}>
              {loading ? <span className="spinner" /> : t("onboarding.continue")}
            </button>
          </form>
        )}

        {/* Step 2: Connect Google */}
        {step === 2 && (
          <div
            className="glass-card-static animate-fade-in"
            style={{
              padding: "32px 28px",
              display: "flex",
              flexDirection: "column",
              gap: "20px",
            }}
          >
            <h2
              style={{
                fontSize: "1.1rem",
                fontWeight: 600,
                color: "var(--color-text-primary)",
              }}
            >
              {t("onboarding.google.title")}
            </h2>

            <ul
              style={{
                listStyle: "none",
                padding: 0,
                display: "flex",
                flexDirection: "column",
                gap: "10px",
              }}
            >
              {(
                [
                  "onboarding.google.bullet1",
                  "onboarding.google.bullet2",
                  "onboarding.google.bullet3",
                ] as const
              ).map((key) => (
                <li
                  key={key}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "10px",
                    fontSize: "0.9rem",
                    color: "var(--color-text-secondary)",
                    lineHeight: 1.6,
                  }}
                >
                  <span style={{ color: "var(--color-jade)", flexShrink: 0 }}>✓</span>
                  {t(key)}
                </li>
              ))}
            </ul>

            <button
              onClick={connectGoogle}
              className="btn-fuji"
              disabled={loading}
              type="button"
              style={{ width: "100%" }}
            >
              <svg viewBox="0 0 24 24" style={{ width: "18px", height: "18px", fill: "currentColor" }} aria-hidden>
                <path d="M21.35 11.1h-9.18v2.98h5.27c-.23 1.51-1.73 4.44-5.27 4.44-3.17 0-5.74-2.63-5.74-5.87s2.57-5.87 5.74-5.87c1.8 0 3.01.77 3.7 1.43l2.52-2.43C16.98 4.5 14.78 3.5 12.17 3.5 7.45 3.5 3.67 7.36 3.67 12.08s3.78 8.58 8.5 8.58c4.91 0 8.17-3.45 8.17-8.3 0-.56-.06-.98-.13-1.26Z" />
              </svg>
              {t("onboarding.google.connect")}
            </button>
          </div>
        )}

        {/* Step 3: Setting up */}
        {step === 3 && (
          <div
            className="glass-card-static animate-fade-in"
            style={{
              padding: "32px 28px",
              display: "flex",
              flexDirection: "column",
              gap: "20px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div className="spinner" />
              <h2
                style={{
                  fontSize: "1.1rem",
                  fontWeight: 600,
                  color: "var(--color-text-primary)",
                }}
              >
                {t("onboarding.step3")}
              </h2>
            </div>

            <ul
              style={{
                listStyle: "none",
                padding: 0,
                display: "flex",
                flexDirection: "column",
                gap: "12px",
              }}
            >
              {progressKeys.map((key, index) => (
                <li key={key} style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <div
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      flexShrink: 0,
                      transition: "all 0.3s ease",
                      background:
                        progress[index] === "done"
                          ? "var(--color-jade)"
                          : progress[index] === "active"
                            ? "var(--color-sakura)"
                            : "var(--color-bg-elevated)",
                      boxShadow:
                        progress[index] === "active"
                          ? "0 0 8px var(--color-sakura-glow)"
                          : "none",
                    }}
                  />
                  <span
                    style={{
                      fontSize: "0.9rem",
                      color:
                        progress[index] === "done"
                          ? "var(--color-jade)"
                          : progress[index] === "active"
                            ? "var(--color-text-primary)"
                            : "var(--color-text-muted)",
                      transition: "color 0.3s ease",
                    }}
                  >
                    {t(key)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Step 4: Done */}
        {step === 4 && (
          <div
            className="glass-card-static animate-fade-in"
            style={{
              padding: "32px 28px",
              display: "flex",
              flexDirection: "column",
              gap: "20px",
              alignItems: "center",
              textAlign: "center",
            }}
          >
            <div
              className="animate-pulse-glow"
              style={{
                width: "56px",
                height: "56px",
                borderRadius: "50%",
                background: "var(--color-jade)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.5rem",
                color: "white",
              }}
            >
              ✓
            </div>

            <h2
              style={{
                fontSize: "1.3rem",
                fontWeight: 700,
                color: "var(--color-text-primary)",
              }}
            >
              {t("onboarding.done.title")}
            </h2>

            {sheetUrl && (
              <a
                href={sheetUrl}
                target="_blank"
                rel="noreferrer"
                style={{
                  fontSize: "0.85rem",
                  color: "var(--color-fuji)",
                  wordBreak: "break-all",
                }}
              >
                {sheetUrl}
              </a>
            )}

            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "8px",
                justifyContent: "center",
              }}
            >
              {["Jobs Masked", "Jobs Raw", "Run Log", "Dashboard"].map((tab) => (
                <span key={tab} className="badge-neutral">
                  {tab}
                </span>
              ))}
            </div>

            <button
              onClick={() => router.push("/dashboard")}
              className="btn-sakura"
              type="button"
              style={{ width: "100%" }}
            >
              {t("onboarding.done.goToDashboard")}
            </button>

            <p style={{ fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
              {t("onboarding.done.dataNote")}
            </p>
          </div>
        )}
      </div>

      {/* Error display */}
      {error && (
        <p
          style={{
            marginTop: "16px",
            fontSize: "0.85rem",
            color: "var(--color-danger)",
            textAlign: "center",
          }}
        >
          {error}
        </p>
      )}
    </div>
  );
}
