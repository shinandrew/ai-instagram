"use client";

import { useState } from "react";
import { api } from "@/lib/api";

interface DownloadButtonProps {
  postId: string;
  imageUrl: string;
  caption: string | null;
}

export function DownloadButton({ postId, imageUrl, caption }: DownloadButtonProps) {
  const [downloading, setDownloading] = useState(false);

  async function handleDownload() {
    if (downloading) return;
    setDownloading(true);
    try {
      // Track the download (fire-and-forget)
      api.trackDownload(postId).catch(() => {});

      // Fetch image directly (R2 URLs are public, no proxy needed)
      const res = await fetch(imageUrl);
      if (!res.ok) throw new Error("fetch failed");
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      const ext = imageUrl.endsWith(".webp") ? "webp" : "jpg";
      a.download = `aigram-${postId.slice(0, 8)}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
    } catch {
      // Fallback: open image directly
      window.open(imageUrl, "_blank");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <button
      onClick={handleDownload}
      disabled={downloading}
      className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors disabled:opacity-50"
      aria-label="Download image"
    >
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
      {downloading ? "…" : "Save"}
    </button>
  );
}
