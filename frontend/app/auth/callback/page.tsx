"use client";

import { useEffect } from "react";

export default function AuthCallbackPage() {
  useEffect(() => {
    const url = new URL(window.location.href);
    const success = url.searchParams.get("success") === "true";
    const sheet_url = url.searchParams.get("sheet_url");
    if (window.opener) {
      window.opener.postMessage({ success, sheet_url }, "*");
    }
    window.close();
  }, []);

  return <p>Finishing Google connection...</p>;
}
