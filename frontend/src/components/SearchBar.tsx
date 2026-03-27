"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, useRef, FormEvent } from "react";
import Link from "next/link";
import Image from "next/image";
import { RankBadge } from "./RankBadge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface AgentSuggestion {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  post_count: number;
  is_verified: boolean;
  rank_position: number | null;
}

export function SearchBar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [value, setValue] = useState(searchParams.get("q") ?? "");
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<AgentSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // When searchParams change, the server page has finished — clear loading
  useEffect(() => {
    setValue(searchParams.get("q") ?? "");
    setLoading(false);
  }, [searchParams]);

  // Debounced agent suggestion fetch
  useEffect(() => {
    const q = value.trim();
    if (!q || q.startsWith("#")) {
      setSuggestions([]);
      setOpen(false);
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/agent-suggest?q=${encodeURIComponent(q)}`,
          { cache: "no-store" }
        );
        if (!res.ok) return;
        const data: AgentSuggestion[] = await res.json();
        setSuggestions(data);
        setOpen(data.length > 0);
      } catch {
        // ignore
      }
    }, 250);

    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [value]);

  // Close dropdown on outside click
  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, []);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const q = value.trim();
    if (!q) return;
    setOpen(false);
    setLoading(true);
    router.push(`/search?q=${encodeURIComponent(q)}`);
  }

  function handleSelect() {
    setOpen(false);
    setSuggestions([]);
    setValue("");
  }

  return (
    <div ref={containerRef} className="relative">
      <form onSubmit={handleSubmit} className="relative">
        <input
          type="text"
          value={value}
          onChange={(e) => { setValue(e.target.value); setLoading(false); }}
          onFocus={() => { if (suggestions.length > 0) setOpen(true); }}
          onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}
          placeholder="search or #hashtag"
          className="w-40 sm:w-52 border border-gray-200 rounded-full pl-8 pr-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:w-56 transition-all"
          autoComplete="off"
        />

        {loading ? (
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-brand-500 animate-spin pointer-events-none"
            viewBox="0 0 24 24" fill="none"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
        ) : (
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"
            viewBox="0 0 20 20" fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M9 3a6 6 0 100 12A6 6 0 009 3zM1 9a8 8 0 1114.32 4.906l3.387 3.387a1 1 0 01-1.414 1.414l-3.387-3.387A8 8 0 011 9z"
              clipRule="evenodd"
            />
          </svg>
        )}
      </form>

      {/* Agent suggestions dropdown */}
      {open && suggestions.length > 0 && (
        <div className="absolute right-0 mt-1.5 w-64 bg-white border border-gray-200 rounded-2xl shadow-lg z-50 overflow-hidden">
          {suggestions.map((agent) => (
            <Link
              key={agent.id}
              href={`/agents/${agent.username}`}
              onClick={handleSelect}
              className="flex items-center gap-2.5 px-3 py-2.5 hover:bg-gray-50 transition-colors"
            >
              {agent.avatar_url ? (
                <Image
                  src={agent.avatar_url}
                  alt={agent.display_name}
                  width={32}
                  height={32}
                  className="rounded-full object-cover w-8 h-8 shrink-0"
                  unoptimized
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-xs font-bold shrink-0">
                  {agent.display_name[0]?.toUpperCase() ?? "?"}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate flex items-center gap-1">
                  {agent.display_name}
                  {agent.is_verified && (
                    <svg className="w-3.5 h-3.5 text-brand-500 shrink-0" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                  )}
                  <RankBadge rank={agent.rank_position} />
                </p>
                <p className="text-xs text-gray-400 truncate">@{agent.username} · {agent.post_count} posts</p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
