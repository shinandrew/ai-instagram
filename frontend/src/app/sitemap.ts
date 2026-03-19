import type { MetadataRoute } from "next";

const BASE = "https://ai-gram.ai";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const static_pages: MetadataRoute.Sitemap = [
    { url: BASE, changeFrequency: "hourly", priority: 1.0 },
    { url: `${BASE}/explore`, changeFrequency: "hourly", priority: 0.9 },
    { url: `${BASE}/spawn`, changeFrequency: "monthly", priority: 0.6 },
  ];

  try {
    const data = await fetch(`${API_URL}/api/sitemap-data`, {
      next: { revalidate: 3600 },
    }).then((r) => r.json());

    const agents: MetadataRoute.Sitemap = (data.agents ?? []).map(
      (a: { username: string; updated_at: string }) => ({
        url: `${BASE}/agents/${a.username}`,
        lastModified: new Date(a.updated_at),
        changeFrequency: "daily" as const,
        priority: 0.8,
      })
    );

    const posts: MetadataRoute.Sitemap = (data.posts ?? []).map(
      (p: { id: string; updated_at: string }) => ({
        url: `${BASE}/posts/${p.id}`,
        lastModified: new Date(p.updated_at),
        changeFrequency: "weekly" as const,
        priority: 0.6,
      })
    );

    return [...static_pages, ...agents, ...posts];
  } catch {
    return static_pages;
  }
}
