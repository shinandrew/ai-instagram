/**
 * First-touch attribution: remember where the visitor originally came from
 * (external referrer + UTM query) so funnel events credit the right channel
 * even after internal navigation.
 */
const KEY = "aigram_first_touch";

export function captureFirstTouch(): void {
  if (typeof window === "undefined") return;
  try {
    if (sessionStorage.getItem(KEY)) return;
    const ref = document.referrer || "";
    const isInternal = ref.includes(window.location.hostname);
    const utm = window.location.search.includes("utm_") ? window.location.search : "";
    const value = (isInternal ? "" : ref) + utm;
    sessionStorage.setItem(KEY, value || "direct");
  } catch {
    /* ignore */
  }
}

export function getFirstTouch(): string {
  if (typeof window === "undefined") return "";
  try {
    captureFirstTouch();
    return sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}
