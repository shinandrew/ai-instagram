"use client";

import { useRouter } from "next/navigation";
import { useLanguage, LANGUAGES } from "./LanguageProvider";

export function LanguageSelector() {
  const { language, setLanguage } = useLanguage();
  const router = useRouter();

  function handleChange(lang: string) {
    setLanguage(lang);
    router.refresh();
  }

  return (
    <div className="flex items-center gap-1 text-sm text-gray-600">
      <span className="text-base leading-none select-none">🌐</span>
      <select
        value={language}
        onChange={(e) => handleChange(e.target.value)}
        className="text-xs border-0 bg-transparent text-gray-700 font-medium focus:outline-none cursor-pointer pr-1"
        aria-label="Feed language"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>{l.label}</option>
        ))}
      </select>
    </div>
  );
}
