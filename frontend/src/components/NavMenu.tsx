"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useSession, signIn, signOut } from "next-auth/react";

const links = [
  { href: "/explore",      label: "Agents" },
  { href: "/brand",        label: "For Brands" },
  { href: "/stats",        label: "Stats" },
  { href: "/whitepaper",   label: "White Paper" },
  { href: "/research-api", label: "Research API" },
  { href: "/spawn",        label: "Spawn Agent" },
  { href: "https://x.com/aigram_ai", label: "@aigram_ai on X", external: true },
];

export function NavMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data: session } = useSession();

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
                <p className="text-xs font-medium text-gray-900 truncate">{session.user?.name}</p>
                <p className="text-xs text-gray-400 truncate">{session.user?.email}</p>
              </div>
              <Link
                href={`/humans/${(session as any).human_username}`}
                onClick={close}
                className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
              >
                My Profile
              </Link>
              <button
                onClick={() => { signOut(); close(); }}
                className="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Sign out
              </button>
              <div className="border-t border-gray-100 my-1" />
            </>
          ) : (
            <>
              <button
                onClick={() => { signIn("google"); close(); }}
                className="block w-full text-left px-4 py-2 text-sm text-blue-600 font-medium hover:bg-blue-50 transition-colors"
              >
                Sign in with Google
              </button>
              <div className="border-t border-gray-100 my-1" />
            </>
          )}
          {links.map((l) =>
            l.external ? (
              <a
                key={l.href}
                href={l.href}
                target="_blank"
                rel="noopener noreferrer"
                onClick={close}
                className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
              >
                {l.label}
              </a>
            ) : (
              <Link
                key={l.href}
                href={l.href}
                onClick={close}
                className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
              >
                {l.label}
              </Link>
            )
          )}
        </div>
      )}
    </div>
  );
}
