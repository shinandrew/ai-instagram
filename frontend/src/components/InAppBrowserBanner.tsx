"use client";

import { useEffect, useState } from "react";

function detectInAppBrowser(): string | null {
  if (typeof navigator === "undefined") return null;
  const ua = navigator.userAgent;
  if (/Instagram/i.test(ua)) return "Instagram";
  if (/FBAN|FBAV/i.test(ua)) return "Facebook";
  if (/\bTwitter\b/i.test(ua)) return "X (Twitter)";
  if (/Line\//i.test(ua)) return "LINE";
  if (/KAKAOTALK/i.test(ua)) return "KakaoTalk";
  if (/Snapchat/i.test(ua)) return "Snapchat";
  if (/TikTok/i.test(ua)) return "TikTok";
  // Generic Android WebView
  if (/Android/i.test(ua) && /wv\b/.test(ua)) return "an in-app browser";
  return null;
}

export function InAppBrowserBanner() {
  const [app, setApp] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setApp(detectInAppBrowser());
  }, []);

  if (!app) return null;

  const url = typeof window !== "undefined" ? window.location.href : "https://ai-gram.ai";

  function copyUrl() {
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="bg-amber-50 border-b border-amber-200 px-4 py-3">
      <p className="text-xs text-amber-800 font-medium text-center">
        You&apos;re viewing this in {app}. Google sign-in is blocked in in-app browsers.
      </p>
      <p className="text-xs text-amber-700 text-center mt-0.5">
        Open in <strong>Safari</strong> or <strong>Chrome</strong> to sign in.
      </p>
      <div className="flex justify-center mt-2">
        <button
          onClick={copyUrl}
          className="text-xs bg-amber-100 hover:bg-amber-200 border border-amber-300 text-amber-900 font-medium px-3 py-1 rounded-lg transition-colors"
        >
          {copied ? "Copied!" : "Copy link to open in browser"}
        </button>
      </div>
    </div>
  );
}
