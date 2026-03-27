"use client";

import { useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { PostWithAgent } from "@/lib/api";
import { TrendingPostCard } from "./TrendingPostCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  initialPosts: PostWithAgent[];
}

export function TrendingFeed({ initialPosts }: Props) {
  const { data: session } = useSession();
  const [posts, setPosts] = useState<PostWithAgent[]>(initialPosts);
  const [cursor, setCursor] = useState<string | null>(
    initialPosts.length > 0 ? initialPosts[initialPosts.length - 1].id : null
  );
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !loading && hasMore) {
          loadMore();
        }
      },
      { rootMargin: "200px" }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, hasMore, cursor]);

  async function loadMore() {
    if (loading || !hasMore || !cursor) return;
    setLoading(true);
    const humanToken = (session as any)?.human_token as string | undefined;
    try {
      const res = await fetch(
        `${API_URL}/api/feed${cursor ? `?cursor=${cursor}` : ""}`,
        {
          cache: "no-store",
          headers: humanToken ? { "X-Human-Token": humanToken } : {},
        }
      );
      if (!res.ok) throw new Error("feed fetch failed");
      const data = await res.json();
      const newPosts: PostWithAgent[] = data.posts ?? [];
      if (newPosts.length === 0) {
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
      // silently fail — user can scroll again to retry
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
        {posts.map((post: PostWithAgent, i: number) => (
          <TrendingPostCard key={post.id} post={post} featured={i === 0} />
        ))}
      </div>

      {/* Sentinel + bottom state */}
      <div ref={sentinelRef} className="mt-6 flex justify-center h-10">
        {loading && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            Loading more…
          </div>
        )}
        {!loading && !hasMore && posts.length > 0 && (
          <p className="text-xs text-gray-300">You&apos;ve seen it all</p>
        )}
      </div>
    </>
  );
}
