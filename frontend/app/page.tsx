"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useLocale } from "@/lib/i18n";
import LanguageToggle from "@/components/LanguageToggle";

function SakuraPetals() {
  const [petals, setPetals] = useState<{ id: number; left: string; delay: string; duration: string; size: number }[]>([]);

  useEffect(() => {
    const p = Array.from({ length: 15 }, (_, i) => ({
      id: i,
      left: `${Math.random() * 100}%`,
      delay: `${Math.random() * 8}s`,
      duration: `${8 + Math.random() * 6}s`,
      size: 8 + Math.random() * 10,
    }));
    setPetals(p);
  }, []);

  return (
    <>
      {petals.map((p) => (
        <div
          key={p.id}
          className="petal"
          style={{
            left: p.left,
            animationDelay: p.delay,
            animationDuration: p.duration,
            width: `${p.size}px`,
            height: `${p.size}px`,
          }}
        />
      ))}
    </>
  );
}

export default function Home() {
  const { t } = useLocale();

  return (
    <div className="bg-seigaiha" style={{ minHeight: "100vh", position: "relative", overflow: "hidden" }}>
      <SakuraPetals />

      {/* Top bar */}
      <header
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "20px 40px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontSize: "24px" }}>🏥</span>
          <span style={{ fontWeight: 700, fontSize: "1.1rem", color: "var(--color-text-primary)" }}>
            {t("app.title")}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <LanguageToggle />
          <Link href="/login" className="btn-ghost btn-sm" style={{ textDecoration: "none" }}>
            {t("landing.cta.login")}
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          padding: "80px 24px 60px",
          maxWidth: "800px",
          margin: "0 auto",
        }}
      >
        <div className="animate-fade-in">
          <h1
            style={{
              fontSize: "clamp(2.2rem, 5vw, 3.5rem)",
              fontWeight: 700,
              lineHeight: 1.3,
              color: "var(--color-text-primary)",
              whiteSpace: "pre-line",
            }}
          >
            {t("landing.hero")}
          </h1>
        </div>

        <p
          className="animate-fade-in-delay-1"
          style={{
            fontSize: "1.15rem",
            color: "var(--color-text-secondary)",
            marginTop: "24px",
            maxWidth: "560px",
            lineHeight: 1.8,
          }}
        >
          {t("landing.heroSub")}
        </p>

        <div
          className="animate-fade-in-delay-2"
          style={{
            display: "flex",
            gap: "16px",
            marginTop: "40px",
            flexWrap: "wrap",
            justifyContent: "center",
          }}
        >
          <Link href="/login" className="btn-sakura" style={{ textDecoration: "none" }}>
            {t("landing.cta.start")}
          </Link>
          <Link href="/login" className="btn-ghost" style={{ textDecoration: "none" }}>
            {t("landing.cta.login")}
          </Link>
        </div>
      </section>

      {/* Feature cards */}
      <section
        style={{
          position: "relative",
          zIndex: 10,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: "24px",
          maxWidth: "900px",
          margin: "0 auto",
          padding: "20px 24px 80px",
        }}
      >
        {[
          {
            icon: "🔍",
            titleKey: "landing.feature1.title" as const,
            descKey: "landing.feature1.desc" as const,
          },
          {
            icon: "🛡️",
            titleKey: "landing.feature2.title" as const,
            descKey: "landing.feature2.desc" as const,
          },
          {
            icon: "📊",
            titleKey: "landing.feature3.title" as const,
            descKey: "landing.feature3.desc" as const,
          },
        ].map((feature, i) => (
          <div
            key={feature.titleKey}
            className={`glass-card animate-fade-in-delay-${i + 1}`}
            style={{ padding: "28px 24px" }}
          >
            <div
              style={{
                fontSize: "2rem",
                marginBottom: "16px",
              }}
            >
              {feature.icon}
            </div>
            <h3
              style={{
                fontSize: "1.05rem",
                fontWeight: 600,
                color: "var(--color-text-primary)",
                marginBottom: "8px",
              }}
            >
              {t(feature.titleKey)}
            </h3>
            <p
              style={{
                fontSize: "0.9rem",
                color: "var(--color-text-secondary)",
                lineHeight: 1.7,
              }}
            >
              {t(feature.descKey)}
            </p>
          </div>
        ))}
      </section>

      {/* Footer accent line */}
      <div
        style={{
          height: "2px",
          background:
            "linear-gradient(90deg, transparent, var(--color-sakura), var(--color-fuji), transparent)",
          margin: "0 auto",
          maxWidth: "400px",
        }}
      />
    </div>
  );
}
