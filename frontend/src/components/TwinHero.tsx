"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { captureFirstTouch } from "@/lib/firstTouch";
import { useT } from "@/components/LanguageProvider";

/**
 * Landing-page hero: enter an X handle → instant twin preview, no account.
 * Routes to /spawn/twin?handle=… which auto-starts the public preview.
 */
export function TwinHero() {
  const [handle, setHandle] = useState("");
  const router = useRouter();
  const t = useT();

  // Remember the external referrer before any internal navigation overwrites it
  useEffect(() => { captureFirstTouch(); }, []);

  const go = () => {
    const h = handle.trim().replace(/^@/, "");
    if (!h) return;
    router.push(`/spawn/twin?handle=${encodeURIComponent(h)}`);
  };

  return (
    <div className="w-full max-w-md mx-auto">
      <h2 className="text-2xl sm:text-3xl font-extrabold text-gray-900 tracking-tight">
        {t.preview_hero_title ?? "Meet your AI twin"}
      </h2>
      <p className="mt-1.5 text-sm text-gray-500 max-w-sm mx-auto">
        {t.preview_hero_sub ?? "Enter your X handle and watch your twin come to life — no account needed."}
      </p>
      <div className="mt-4 flex gap-2">
        <div className="relative flex-1">
          <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 font-medium select-none">@</span>
          <input
            type="text"
            value={handle}
            onChange={(e) => setHandle(e.target.value.replace(/^@/, ""))}
            onKeyDown={(e) => e.key === "Enter" && go()}
            placeholder={t.preview_hero_placeholder ?? "your X handle"}
            className="w-full pl-8 pr-4 py-3 border border-gray-200 rounded-full text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-400 shadow-sm"
          />
        </div>
        <button
          onClick={go}
          disabled={!handle.trim()}
          className="px-5 py-3 bg-black text-white rounded-full font-semibold text-sm hover:bg-zinc-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap shadow-sm"
        >
          {t.preview_hero_button ?? "Generate my twin"}
        </button>
      </div>
      <p className="mt-2 text-xs text-gray-400">
        {t.twin_public_note} {t.preview_expiry_note ?? "Unclaimed twins fade away after 24 hours."}
      </p>
    </div>
  );
}
