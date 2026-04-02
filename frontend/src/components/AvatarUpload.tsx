"use client";

import { useState, useRef } from "react";
import { api } from "@/lib/api";

interface Props {
  initialUrl: string | null;
  displayName: string;
  humanToken: string;
}

export function AvatarUpload({ initialUrl, displayName, humanToken }: Props) {
  const [avatarUrl, setAvatarUrl] = useState<string | null>(initialUrl);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setError("File too large (max 10 MB)");
      return;
    }

    setUploading(true);
    setError(null);

    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const dataUrl = reader.result as string;
        // Strip the "data:image/...;base64," prefix
        const base64 = dataUrl.split(",")[1];
        const result = await api.uploadHumanAvatar(base64, humanToken);
        setAvatarUrl(result.avatar_url);
      } catch (err: any) {
        setError(err?.message ?? "Upload failed");
      } finally {
        setUploading(false);
        // reset so same file can be re-selected
        if (inputRef.current) inputRef.current.value = "";
      }
    };
    reader.readAsDataURL(file);
  }

  return (
    <div className="relative group cursor-pointer" onClick={() => !uploading && inputRef.current?.click()}>
      {avatarUrl ? (
        <img
          src={avatarUrl}
          alt={displayName}
          className="rounded-full object-cover w-24 h-24 border-4 border-gray-300"
        />
      ) : (
        <div className="w-24 h-24 rounded-full bg-gradient-to-br from-gray-400 to-gray-200 flex items-center justify-center text-white text-3xl font-bold border-4 border-gray-300">
          {displayName[0]?.toUpperCase() ?? "?"}
        </div>
      )}

      {/* Hover overlay */}
      <div className="absolute inset-0 rounded-full bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
        {uploading ? (
          <svg className="w-6 h-6 text-white animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        ) : (
          <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFile}
      />

      {error && (
        <p className="absolute top-full mt-1 left-1/2 -translate-x-1/2 text-xs text-red-500 whitespace-nowrap">
          {error}
        </p>
      )}
    </div>
  );
}
