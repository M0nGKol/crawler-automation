"use client";

import { useEffect } from "react";

export default function OnboardingCallbackPage() {
  useEffect(() => {
    const url = new URL(window.location.href);
    const success = url.searchParams.get("success") === "true";
    const sheetUrl = url.searchParams.get("sheet_url");
    const error = url.searchParams.get("error");
    if (window.opener) {
      if (success) {
        window.opener.postMessage({ success: true, sheet_url: sheetUrl }, "*");
      } else {
        window.opener.postMessage({ success: false, error }, "*");
      }
    }
    const timeout = setTimeout(() => window.close(), 500);
    return () => clearTimeout(timeout);
  }, []);

  return <main className="p-6">Completing onboarding...</main>;
}
