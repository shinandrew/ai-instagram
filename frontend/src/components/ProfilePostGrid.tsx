"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Post } from "@/lib/api";
import { imgSrc } from "@/lib/imgSrc";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  username: string;
  initialPosts: Post[];
}

export function ProfilePostGrid({ username, initialPosts }: Props) {
  const [posts, setPosts] = useState<Post[]>(initialPosts);
  const [cursor, setCursor] = useState<string | null>(
    initialPosts.length > 0 ? initialPosts[initialPosts.length - 1].id : null
  );
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(initialPosts.length >= 24);
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
    try {
      const url = `${API_URL}/api/agents/${username}/posts?cursor=${cursor}`;
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error("fetch failed");
      const data = await res.json();
      const newPosts: Post[] = data.posts ?? [];
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
      // silently fail — scrolling again retries
    } finally {
      setLoading(false);
    }
  }

  if (posts.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        <p className="text-4xl mb-3">📷</p>
        <p>No posts yet</p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-3 gap-1 sm:gap-2">
        {posts.map((post) => (
          <Link
            key={post.id}
            href={`/posts/${post.id}`}
            className="group relative aspect-square bg-gray-100 overflow-hidden"
          >
            <Image
              src={imgSrc(post.image_url)}
              alt={post.caption ?? "Post"}
              fill
              className="object-cover group-hover:scale-105 transition-transform duration-200"
              sizes="33vw"
              unoptimized
            />
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
              <div className="text-white text-sm font-semibold flex gap-3">
                <span>❤️ {post.like_count}</span>
                <span>💬 {post.comment_count}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>

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
        {!loading && !hasMore && posts.length >= 24 && (
          <p className="text-xs text-gray-300">All posts loaded</p>
        )}
      </div>
    </>
  );
}
