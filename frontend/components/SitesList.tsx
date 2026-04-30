"use client";

interface Site {
  id: string;
  site_name: string;
  url: string;
  type: string;
  is_active: boolean;
  is_default: boolean;
}

export function SitesList({ sites: initialSites }: { sites: Site[] }) {
  const sites = initialSites;

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

          <div />
        </div>
      ))}
    </div>
  );
}

