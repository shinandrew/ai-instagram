"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";

export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "ja", label: "日本語" },
  { code: "ko", label: "한국어" },
  { code: "zh", label: "中文" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
  { code: "pt", label: "Português" },
];

const COOKIE_NAME = "aigram_lang";

interface LanguageContextValue {
  language: string;
  setLanguage: (lang: string) => void;
}

const LanguageContext = createContext<LanguageContextValue>({
  language: "en",
  setLanguage: () => {},
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState("en");

  useEffect(() => {
    // Read from cookie on mount
    const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE_NAME}=([^;]*)`));
    if (match) setLanguageState(decodeURIComponent(match[1]));
  }, []);

  function setLanguage(lang: string) {
    setLanguageState(lang);
    const maxAge = 365 * 24 * 3600;
    document.cookie = `${COOKIE_NAME}=${encodeURIComponent(lang)}; path=/; max-age=${maxAge}; SameSite=Lax`;
  }

  return (
    <LanguageContext.Provider value={{ language, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}
