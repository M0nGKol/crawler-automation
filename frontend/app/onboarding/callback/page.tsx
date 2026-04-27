"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { setStoredToken } from "@/lib/api";

export default function OnboardingCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const success = params.get("success");
    const error = params.get("error");
    const userId = params.get("user_id");

    if (error) {
      console.error("OAuth error:", error);
      router.push("/onboarding?error=" + error);
      return;
    }

    if (token) {
      setStoredToken(token);
      if (userId) localStorage.setItem("user_id", userId);
    }

    if (success === "true" || token) {
      router.push("/dashboard");
    } else {
      router.push("/onboarding?error=auth_failed");
    }
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-black text-white">
      <p>Completing onboarding...</p>
    </div>
  );
}
