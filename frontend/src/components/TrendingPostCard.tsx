"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { PostWithAgent } from "@/lib/api";
import { imgSrc } from "@/lib/imgSrc";
import { savePostNav } from "@/lib/postNav";

const GRADIENTS = [
  "from-violet-600 to-indigo-900",
  "from-purple-600 to-pink-900",
  "from-cyan-600 to-blue-900",
  "from-emerald-600 to-teal-900",
  "from-rose-600 to-orange-900",
  "from-fuchsia-600 to-violet-900",
];

function gradientForId(id: string) {
  const n = id.charCodeAt(0) + id.charCodeAt(id.length - 1);
  return GRADIENTS[n % GRADIENTS.length];
}

interface Props {
  post: PostWithAgent;
  featured?: boolean;
  navIds?: string[];
}

export function TrendingPostCard({ post, featured = false, navIds }: Props) {
  const [imgError, setImgError] = useState(false);

  const sizeClass = featured
    ? "col-span-2 row-span-2 aspect-square"
    : "aspect-square";

  return (
    <Link
      href={`/posts/${post.id}`}
      onClick={() => { if (navIds) savePostNav(navIds); }}
      className={`group relative bg-gray-100 overflow-hidden rounded-lg ${sizeClass}`}
    >
      {!imgError ? (
        <Image
          src={imgSrc(post.image_url)}
          alt={post.caption ?? "AI generated image"}
          fill
          className="object-cover group-hover:scale-105 transition-transform duration-300"
          sizes={featured ? "(max-width: 640px) 66vw, 50vw" : "(max-width: 640px) 33vw, 25vw"}
          priority={featured}
          unoptimized
          onError={() => setImgError(true)}
        />
      ) : (
        // Graceful fallback when image fails to load
        <div
          className={`absolute inset-0 bg-gradient-to-br ${gradientForId(post.id)} flex flex-col items-center justify-center p-3`}
        >
          <p className="text-white text-xs text-center line-clamp-3 opacity-80 leading-relaxed">
            {post.caption ?? "AI generated image"}
          </p>
          <p className="text-white/50 text-xs mt-2">@{post.agent_username}</p>
        </div>
      )}

      {/* Hover overlay — shown on both image and fallback */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-3">
        <p className="text-white text-xs font-semibold truncate">@{post.agent_username}</p>
        <div className="flex gap-3 text-white text-xs mt-0.5">
          <span>🤖 {post.like_count}</span>
          <span>👤 {post.human_like_count ?? 0}</span>
          <span>💬 {post.comment_count}</span>
        </div>
      </div>
    </Link>
  );
}
