"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

interface Site {
  id: string;
  site_name: string;
  url: string;
  type: string;
  is_active: boolean;
  is_default: boolean;
}

export function SitesList({ sites: initialSites }: { sites: Site[] }) {
  const [sites, setSites] = useState(initialSites);
  const [loading, setLoading] = useState<string | null>(null);

  const toggleSite = async (siteId: string, currentActive: boolean) => {
    setLoading(siteId);
    try {
      const res = await apiFetch(`/sites/${siteId}`, {
        method: "PUT",
        body: JSON.stringify({ is_active: !currentActive }),
      });

      if (!res.ok) throw new Error("Toggle failed");

      setSites((prev) =>
        prev.map((s) => (s.id === siteId ? { ...s, is_active: !currentActive } : s))
      );
    } catch {
      // Silently ignore toggle failures in production UI.
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="space-y-2">
      {sites.map((site) => (
        <div
          key={site.id}
          className="flex items-center justify-between px-4 py-3 rounded-lg bg-gray-800 hover:bg-gray-750"
        >
          <div className="flex flex-col">
            <span className="text-sm font-medium text-white">{site.site_name}</span>
            <span className="text-xs text-gray-400">{site.url}</span>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">{site.type}</span>

            <button
              onClick={() => void toggleSite(site.id, site.is_active)}
              disabled={loading === site.id}
              className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors duration-200 focus:outline-none ${
                site.is_active ? "bg-pink-500" : "bg-gray-600"
              } ${loading === site.id ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
              aria-label={`Toggle ${site.site_name}`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
                  site.is_active ? "translate-x-5" : "translate-x-1"
                }`}
              />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

