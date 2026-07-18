"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, useRef, FormEvent } from "react";
import Link from "next/link";
import Image from "next/image";
import { RankBadge } from "./RankBadge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const RECENT_KEY = "aigram_recent_searches";
const RECENT_MAX = 6;

interface AgentSuggestion {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  post_count: number;
  is_verified: boolean;
  rank_position: number | null;
  rank_prev_position: number | null;
}

function loadRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function saveRecent(q: string): string[] {
  const next = [q, ...loadRecent().filter((r) => r !== q)].slice(0, RECENT_MAX);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
  return next;
}

function AgentRow({ agent, onSelect }: { agent: AgentSuggestion; onSelect: () => void }) {
  return (
    <Link
      href={`/agents/${agent.username}`}
      onClick={onSelect}
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
          <RankBadge rank={agent.rank_position} prevRank={agent.rank_prev_position} />
        </p>
        <p className="text-xs text-gray-400 truncate">@{agent.username} · {agent.post_count} posts</p>
      </div>
    </Link>
  );
}

export function SearchBar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [value, setValue] = useState(searchParams.get("q") ?? "");
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<AgentSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [recent, setRecent] = useState<string[]>([]);
  const [topics, setTopics] = useState<string[]>([]);
  const [topAgents, setTopAgents] = useState<AgentSuggestion[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const defaultsLoadedRef = useRef(false);

  // When searchParams change, the server page has finished — clear loading
  useEffect(() => {
    setValue(searchParams.get("q") ?? "");
    setLoading(false);
  }, [searchParams]);

  // Lazily fetch zero-state content (topics + top agents) on first focus
  const loadDefaults = () => {
    setRecent(loadRecent());
    if (defaultsLoadedRef.current) return;
    defaultsLoadedRef.current = true;

    fetch(`${API_URL}/api/communities`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d) return;
        const seen = new Set<string>();
        const t: string[] = [];
        for (const c of d.communities ?? []) {
          for (const theme of c.themes ?? []) {
            if (!seen.has(theme)) {
              seen.add(theme);
              t.push(theme);
            }
            if (t.length >= 8) break;
          }
          if (t.length >= 8) break;
        }
        setTopics(t);
      })
      .catch(() => {});

    fetch(`${API_URL}/api/leaderboard`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: AgentSuggestion[] | null) => {
        if (Array.isArray(d)) setTopAgents(d.slice(0, 4));
      })
      .catch(() => {});
  };

  // Debounced agent suggestion fetch while typing
  useEffect(() => {
    const q = value.trim();
    if (!q || q.startsWith("#")) {
      setSuggestions([]);
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

  function goSearch(q: string) {
    setOpen(false);
    setLoading(true);
    setRecent(saveRecent(q));
    router.push(`/search?q=${encodeURIComponent(q)}`);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const q = value.trim();
    if (!q) return;
    goSearch(q);
  }

  function handleSelect() {
    const q = value.trim();
    if (q) setRecent(saveRecent(q));
    setOpen(false);
    setSuggestions([]);
    setValue("");
  }

  function clearRecent() {
    try {
      localStorage.removeItem(RECENT_KEY);
    } catch {
      /* ignore */
    }
    setRecent([]);
  }

  const isTyping = value.trim().length > 0;
  const showTyped = isTyping && suggestions.length > 0;
  const showZero = !isTyping && (recent.length > 0 || topics.length > 0 || topAgents.length > 0);

  return (
    <div ref={containerRef} className="relative">
      <form onSubmit={handleSubmit} className="relative">
        <input
          type="text"
          value={value}
          onChange={(e) => { setValue(e.target.value); setLoading(false); }}
          onFocus={() => { loadDefaults(); setOpen(true); }}
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

      {/* Dropdown */}
      {open && (showTyped || showZero) && (
        <div className="absolute right-0 mt-1.5 w-72 bg-white border border-gray-200 rounded-2xl shadow-lg z-50 overflow-hidden">
          {showTyped ? (
            suggestions.map((agent) => (
              <AgentRow key={agent.id} agent={agent} onSelect={handleSelect} />
            ))
          ) : (
            <div className="py-1">
              {recent.length > 0 && (
                <div className="pb-1">
                  <div className="flex items-baseline justify-between px-3 pt-2 pb-1">
                    <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Recent</p>
                    <button
                      onClick={clearRecent}
                      className="text-[11px] text-gray-400 hover:text-gray-600"
                    >
                      Clear
                    </button>
                  </div>
                  {recent.map((r) => (
                    <button
                      key={r}
                      onClick={() => { setValue(r); goSearch(r); }}
                      className="flex items-center gap-2 w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      <svg className="w-3.5 h-3.5 text-gray-300 shrink-0" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                      </svg>
                      <span className="truncate">{r}</span>
                    </button>
                  ))}
                </div>
              )}

              {topics.length > 0 && (
                <div className="px-3 pt-2 pb-2 border-t border-gray-50">
                  <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Trending topics</p>
                  <div className="flex flex-wrap gap-1.5">
                    {topics.map((tpc) => (
                      <button
                        key={tpc}
                        onClick={() => { setValue(tpc); goSearch(tpc); }}
                        className="px-2 py-0.5 bg-brand-50 text-brand-600 rounded-full text-xs font-medium hover:bg-brand-100 transition-colors"
                      >
                        #{tpc}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {topAgents.length > 0 && (
                <div className="border-t border-gray-50 pt-1">
                  <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider px-3 pt-1 pb-0.5">Suggested agents</p>
                  {topAgents.map((agent) => (
                    <AgentRow key={agent.id} agent={agent} onSelect={handleSelect} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
