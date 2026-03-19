"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, FormEvent } from "react";

export function SearchBar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [value, setValue] = useState(searchParams.get("q") ?? "");
  const [loading, setLoading] = useState(false);

  // When searchParams change, the server page has finished — clear loading
  useEffect(() => {
    setValue(searchParams.get("q") ?? "");
    setLoading(false);
  }, [searchParams]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const q = value.trim();
    if (!q) return;
    setLoading(true);
    router.push(`/search?q=${encodeURIComponent(q)}`);
  }

  return (
    <form onSubmit={handleSubmit} className="relative">
      <input
        type="text"
        value={value}
        onChange={(e) => { setValue(e.target.value); setLoading(false); }}
        placeholder="search or #hashtag"
        className="w-40 sm:w-52 border border-gray-200 rounded-full pl-8 pr-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:w-56 transition-all"
      />

      {/* Spinner while loading, search icon otherwise */}
      {loading ? (
        <svg
          className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-brand-500 animate-spin pointer-events-none"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
      ) : (
        <svg
          className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M9 3a6 6 0 100 12A6 6 0 009 3zM1 9a8 8 0 1114.32 4.906l3.387 3.387a1 1 0 01-1.414 1.414l-3.387-3.387A8 8 0 011 9z"
            clipRule="evenodd"
          />
        </svg>
      )}
    </form>
  );
}
