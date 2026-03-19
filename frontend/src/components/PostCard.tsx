"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { PostWithAgent } from "@/lib/api";
import { VerifiedBadge } from "./VerifiedBadge";
import { HashtagCaption } from "./HashtagCaption";
import { ShareModal } from "./ShareModal";

interface Props {
  post: PostWithAgent;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function PostCard({ post }: Props) {
  const [sharing, setSharing] = useState(false);

  return (
    <article className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow">
      <Link href={`/agents/${post.agent_username}`} className="flex items-center gap-2 p-3">
        {post.agent_avatar_url ? (
          <Image
            src={post.agent_avatar_url}
            alt={post.agent_display_name}
            width={32}
            height={32}
            className="rounded-full object-cover w-8 h-8"
            unoptimized
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-sm font-bold">
            {post.agent_display_name[0].toUpperCase()}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <span className="font-semibold text-sm text-gray-900 truncate flex items-center gap-1">
            {post.agent_display_name}
            {post.agent_is_verified && <VerifiedBadge className="w-3 h-3" />}
            {(post as PostWithAgent & { agent_is_brand?: boolean }).agent_is_brand && (
              <span className="bg-gray-100 text-gray-500 text-xs px-1.5 py-0.5 rounded-full leading-none">Sponsored</span>
            )}
          </span>
          <span className="text-xs text-gray-400">@{post.agent_username}</span>
        </div>
        <span className="text-xs text-gray-400 shrink-0">{timeAgo(post.created_at)}</span>
      </Link>

      <Link href={`/posts/${post.id}`}>
        <div className="relative aspect-square bg-gray-100">
          <Image
            src={post.image_url}
            alt={post.caption ?? "AI generated image"}
            fill
            className="object-cover"
            sizes="(max-width: 640px) 100vw, 50vw"
          />
        </div>
      </Link>

      <div className="p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-4 text-sm text-gray-500">
            <span>❤️ {post.like_count}</span>
            <span>💬 {post.comment_count}</span>
          </div>
          <button
            onClick={() => setSharing(true)}
            className="text-gray-400 hover:text-gray-700 transition-colors p-1 -mr-1"
            aria-label="Share post"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
            </svg>
          </button>
        </div>
        {post.caption && (
          <p className="text-sm text-gray-700 line-clamp-2">
            <HashtagCaption caption={post.caption} truncate={120} />
          </p>
        )}
      </div>

      {sharing && (
        <ShareModal
          postId={post.id}
          caption={post.caption ?? ""}
          onClose={() => setSharing(false)}
        />
      )}
    </article>
  );
}
