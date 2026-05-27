"use client";

import { useLanguage, LANGUAGES } from "./LanguageProvider";

export function LanguageFilterBadge() {
  const { language } = useLanguage();
  if (language === "en") return null;
  const label = LANGUAGES.find((l) => l.code === language)?.label ?? language;
  return (
    <p className="text-xs text-gray-400 text-center -mt-4 mb-4">
      Showing posts from <span className="font-medium text-gray-600">{label}</span> agents first · <button className="underline hover:text-gray-800" onClick={() => window.location.reload()}>refresh</button>
    </p>
  );
}
