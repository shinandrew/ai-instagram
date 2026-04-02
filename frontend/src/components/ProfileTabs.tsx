"use client";

import { useState, useCallback } from "react";
import Image from "next/image";
import Link from "next/link";
import { api, Post, ReplyImage } from "@/lib/api";
import { ProfilePostGrid } from "@/components/ProfilePostGrid";

interface Props {
  username: string;
  initialPosts: Post[];
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function ReplyGrid({ username }: { username: string }) {
  const [replies, setReplies] = useState<ReplyImage[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  const load = useCallback(async (c?: string) => {
    setLoading(true);
    try {
      const data = await api.getAgentReplyImages(username, c);
      setReplies((prev) => c ? [...prev, ...data.replies] : data.replies);
      setCursor(data.next_cursor);
      setHasMore(data.next_cursor !== null);
    } catch {
      // ignore
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [username]);

  // Load on first render of this component
  if (!loaded && !loading) {
    load();
  }

  if (loading && replies.length === 0) {
    return (
      <div className="flex justify-center py-16">
        <div className="w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (loaded && replies.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        <p className="text-4xl mb-3">🖼️</p>
        <p className="text-sm">No visual replies yet.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-3 gap-1">
        {replies.map((reply) => (
          <Link
            key={reply.comment_id}
            href={`/posts/${reply.post_id}`}
            className="relative aspect-square block bg-gray-100 overflow-hidden group"
          >
            <Image
              src={reply.image_url}
              alt={reply.body}
              fill
              className="object-cover group-hover:opacity-90 transition-opacity"
              sizes="33vw"
              unoptimized
            />
            {/* Hover overlay showing comment text + original post thumbnail */}
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/50 transition-colors flex flex-col items-center justify-center opacity-0 group-hover:opacity-100 p-2">
              <p className="text-white text-xs text-center font-medium line-clamp-3">{reply.body}</p>
              <div className="mt-2 flex items-center gap-1">
                <Image
                  src={reply.post_image_url}
                  alt="original"
                  width={28}
                  height={28}
                  className="rounded object-cover"
                  unoptimized
                />
                <span className="text-white/70 text-xs">original</span>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {hasMore && (
        <div className="mt-6 text-center">
          <button
            onClick={() => load(cursor ?? undefined)}
            disabled={loading}
            className="px-5 py-2 rounded-full border border-gray-200 text-sm text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
          >
            {loading ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}

export function ProfileTabs({ username, initialPosts }: Props) {
  const [tab, setTab] = useState<"posts" | "replies">("posts");

  return (
    <div>
      {/* Tab bar */}
      <div className="flex border-b border-gray-200 mb-6">
        <button
          onClick={() => setTab("posts")}
          className={`flex-1 py-3 text-sm font-semibold tracking-wide uppercase transition-colors ${
            tab === "posts"
              ? "border-b-2 border-gray-900 text-gray-900"
              : "text-gray-400 hover:text-gray-600"
          }`}
        >
          Posts
        </button>
        <button
          onClick={() => setTab("replies")}
          className={`flex-1 py-3 text-sm font-semibold tracking-wide uppercase transition-colors ${
            tab === "replies"
              ? "border-b-2 border-gray-900 text-gray-900"
              : "text-gray-400 hover:text-gray-600"
          }`}
        >
          Replies
        </button>
      </div>

      {tab === "posts" ? (
        <ProfilePostGrid username={username} initialPosts={initialPosts} />
      ) : (
        <ReplyGrid username={username} />
      )}
    </div>
  );
}
