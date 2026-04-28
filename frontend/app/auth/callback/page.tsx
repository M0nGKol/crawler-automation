"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { setStoredToken } from "@/lib/api";

export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    const url = new URL(window.location.href);
    const success = url.searchParams.get("success") === "true";
    const token = url.searchParams.get("token");
    const error = url.searchParams.get("error");
    const userId = url.searchParams.get("user_id");
    const returnTo = url.searchParams.get("return_to") || "/dashboard";

    if (token) {
      setStoredToken(token);
    }
    if (userId) {
      localStorage.setItem("user_id", userId);
      localStorage.setItem("backend_user_id", userId);
    }

    if (window.opener) {
      window.opener.postMessage(
        { success, error, user_id: userId, return_to: returnTo, sheet_url: url.searchParams.get("sheet_url") },
        "*",
      );
      window.close();
      return;
    }

    if (error) {
      router.replace(`${returnTo}${returnTo.includes("?") ? "&" : "?"}error=${encodeURIComponent(error)}`);
      return;
    }

    router.replace(returnTo);
  }, [router]);

  return <p>Finishing Google connection...</p>;
}
