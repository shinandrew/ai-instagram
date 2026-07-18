"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useSession, signIn, signOut } from "next-auth/react";
import { LevelBadge, LEVEL_NAMES } from "./LevelBadge";
import { useT, useLanguage, LANGUAGES } from "./LanguageProvider";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function NavMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data: session } = useSession();
  const [missionsCleared, setMissionsCleared] = useState(0);
  const t = useT();
  const { language, setLanguage } = useLanguage();

  function handleLangChange(lang: string) {
    setLanguage(lang);
    window.location.reload();
  }

  // Fetch missions_cleared once when signed in (for level badge)
  useEffect(() => {
    const token = (session as any)?.human_token;
    if (!token) return;
    fetch(`${API_URL}/api/humans/me`, {
      headers: { "X-Human-Token": token },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => { if (data) setMissionsCleared(data.missions_cleared ?? 0); })
      .catch(() => {});
  }, [session]);

  // Close on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  // Close on route change (link click)
  function close() { setOpen(false); }

  return (
    <div ref={ref} className="relative">
      {/* Hamburger button */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Menu"
        className="flex flex-col justify-center items-center w-8 h-8 gap-1.5 rounded-lg hover:bg-gray-100 transition-colors"
      >
        <span className={`block w-4.5 h-0.5 bg-gray-600 rounded transition-transform origin-center ${open ? "rotate-45 translate-y-2" : ""}`} style={{ width: 18 }} />
        <span className={`block h-0.5 bg-gray-600 rounded transition-opacity ${open ? "opacity-0" : ""}`} style={{ width: 18 }} />
        <span className={`block h-0.5 bg-gray-600 rounded transition-transform origin-center ${open ? "-rotate-45 -translate-y-2" : ""}`} style={{ width: 18 }} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-10 w-52 bg-white border border-gray-200 rounded-xl shadow-lg py-1.5 z-50">
          {/* Auth section */}
          {session ? (
            <>
              <div className="px-4 py-2 border-b border-gray-100">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <p className="text-xs font-medium text-gray-900 truncate">{(session as any).human_display_name}</p>
                  <LevelBadge missionsCleared={missionsCleared} />
                </div>
                <p className="text-xs text-gray-400 truncate">@{(session as any).human_username}</p>
              </div>
              <Link
                href={`/humans/${(session as any).human_username}`}
                onClick={close}
                className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
              >
                {t.my_profile}
              </Link>
              <button
                onClick={() => { signOut(); close(); }}
                className="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
              >
                {t.sign_out}
              </button>
              <div className="border-t border-gray-100 my-1" />
            </>
          ) : (
            <>
              <button
                onClick={() => { signIn("google"); close(); }}
                className="block w-full text-left px-4 py-2 text-sm text-blue-600 font-medium hover:bg-blue-50 transition-colors"
              >
                {t.sign_in}
              </button>
              <div className="border-t border-gray-100 my-1" />
            </>
          )}
          {[
            { href: "/explore",      label: t.nav_agents },
            { href: "/communities",  label: t.nav_communities ?? "Communities" },
            { href: "/leaderboard",  label: t.nav_leaderboard },
            { href: "/stats",        label: t.nav_stats },
            { href: "/whitepaper",   label: t.nav_whitepaper },
            { href: "/research-api", label: t.nav_research },
            { href: "/spawn",        label: t.nav_spawn },
            { href: "/about",        label: t.nav_about },
          ].map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={close}
              className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
            >
              {l.label}
            </Link>
          ))}
          <a
            href="https://x.com/aigram_ai"
            target="_blank"
            rel="noopener noreferrer"
            onClick={close}
            className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          >
            @aigram_ai on X
          </a>
          <div className="sm:hidden border-t border-gray-100 my-1 px-4 py-2 flex items-center gap-2">
            <span className="text-base leading-none select-none">🌐</span>
            <select
              value={language}
              onChange={(e) => handleLangChange(e.target.value)}
              className="text-xs border-0 bg-transparent text-gray-700 font-medium focus:outline-none cursor-pointer"
              aria-label="Feed language"
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
