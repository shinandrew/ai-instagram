const KEY = "post_nav";

export function savePostNav(ids: string[]): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(ids));
  } catch {}
}

export function getPostNav(postId: string): { prev: string | null; next: string | null } {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return { prev: null, next: null };
    const ids: string[] = JSON.parse(raw);
    const idx = ids.indexOf(postId);
    if (idx === -1) return { prev: null, next: null };
    return {
      prev: idx > 0 ? ids[idx - 1] : null,
      next: idx < ids.length - 1 ? ids[idx + 1] : null,
    };
  } catch {
    return { prev: null, next: null };
  }
}
