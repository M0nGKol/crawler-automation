"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function OnboardingCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    const url = new URL(window.location.href);
    const success = url.searchParams.get("success") === "true";
    const sheetUrl = url.searchParams.get("sheet_url");
    const error = url.searchParams.get("error");
    const token = url.searchParams.get("token");

    // If opened as a popup, post message back and close
    if (window.opener) {
      if (success) {
        window.opener.postMessage({ success: true, sheet_url: sheetUrl }, "*");
      } else {
        window.opener.postMessage({ success: false, error }, "*");
      }
      const timeout = setTimeout(() => window.close(), 500);
      return () => clearTimeout(timeout);
    }

    // If opened as a full page redirect (default OAuth flow)
    if (token) {
      localStorage.setItem("auth_token", token);
    }

    if (success || token) {
      router.push("/dashboard");
    } else {
      router.push("/onboarding?error=auth_failed");
    }
  }, [router]);

  return <main className="p-6">Completing onboarding...</main>;
}
