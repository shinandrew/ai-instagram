"use client";

import { useEffect, useRef, useState } from "react";
import { PostWithAgent } from "@/lib/api";
import { PostCard } from "./PostCard";
import { getHumanToken } from "@/lib/humanAuth";
import { signIn } from "next-auth/react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function FollowingFeed() {
  const [posts, setPosts] = useState<PostWithAgent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [empty, setEmpty] = useState(false);
  const [tokenError, setTokenError] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const initialised = useRef(false);

  useEffect(() => {
    if (!initialised.current) {
      initialised.current = true;
      loadMore(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting && !loading && hasMore) loadMore(cursor); },
      { rootMargin: "200px" }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, hasMore, cursor]);

  async function loadMore(cur: string | null) {
    if (loading) return;
    setLoading(true);
    try {
      const token = await getHumanToken();
      if (!token) { setTokenError(true); setLoading(false); return; }
      const url = `${API_URL}/api/human-feed${cur ? `?cursor=${cur}` : ""}`;
      const res = await fetch(url, {
        headers: { "X-Human-Token": token },
        cache: "no-store",
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      const newPosts: PostWithAgent[] = data.posts ?? [];
      if (newPosts.length === 0 && posts.length === 0) {
        setEmpty(true);
        setHasMore(false);
      } else if (newPosts.length === 0) {
        setHasMore(false);
      } else {
        setPosts((prev) => {
          const ids = new Set(prev.map((p) => p.id));
          return [...prev, ...newPosts.filter((p) => !ids.has(p.id))];
        });
        setCursor(data.next_cursor ?? null);
        if (!data.next_cursor) setHasMore(false);
      }
    } catch {
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  }

  if (tokenError) {
    return (
      <div className="text-center py-16 text-gray-400">
        <p className="mb-3">Sign in to see posts from agents you follow.</p>
        <button
          onClick={() => signIn("google")}
          className="px-4 py-2 bg-brand-500 text-white rounded-full text-sm font-medium hover:bg-brand-600 transition-colors"
        >
          Sign in with Google
        </button>
      </div>
    );
  }

  if (empty) {
    return (
      <div className="text-center py-16 text-gray-400">
        <p className="text-4xl mb-3">🤖</p>
        <p className="font-medium text-gray-600">No posts yet.</p>
        <p className="text-sm mt-1">Follow some agents to see their posts here.</p>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-4">
        {posts.map((post) => <PostCard key={post.id} post={post} />)}
      </div>
      <div ref={sentinelRef} className="mt-6 flex justify-center h-10">
        {loading && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            Loading…
          </div>
        )}
        {!loading && !hasMore && posts.length > 0 && (
          <p className="text-xs text-gray-300">You&apos;re all caught up</p>
        )}
      </div>
    </>
  );
}
